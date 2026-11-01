import time
from datetime import timedelta

from sqlalchemy import select

from app.models.billing import EmailMessage
from app.models.user import OneTimeCode, RefreshToken, User
from app.services.email import TEST_OUTBOX
from tests.conftest import PASSWORD, auth, last_code, register

API = "/api/v1"


def test_register_returns_session_and_sends_code(client, db_factory):
    s = register(client, email="  Ada@Example.COM ")
    assert s["user"]["email"] == "ada@example.com"
    assert s["user"]["email_verified"] is False
    assert s["user"]["plan"] == "free"
    assert s["access_token"] and s["refresh_token"]
    assert len(TEST_OUTBOX) == 1 and TEST_OUTBOX[0].to == "ada@example.com"
    with db_factory() as db:
        user = db.execute(select(User)).scalar_one()
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        code = last_code("ada@example.com")
        stored = db.execute(select(OneTimeCode)).scalar_one()
        assert code not in stored.code_hash  # only a keyed hash is stored
        assert db.execute(select(EmailMessage)).scalar_one().status == "accepted"
        assert all(t.token_hash != s["refresh_token"] for t in db.execute(select(RefreshToken)).scalars())


def test_register_rejects_duplicates_weak_passwords_and_bad_timezones(client):
    register(client)
    dup = client.post(f"{API}/auth/register", json={"email": "ADA@example.com", "password": PASSWORD, "first_name": "A"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"
    weak = client.post(f"{API}/auth/register", json={"email": "b@example.com", "password": "short", "first_name": "B"})
    assert weak.status_code == 422
    assert "short" not in weak.text  # submitted values are never echoed
    tz = client.post(f"{API}/auth/register",
                     json={"email": "c@example.com", "password": PASSWORD, "first_name": "C", "timezone": "Mars/Base"})
    assert tz.status_code == 422


def test_unverified_user_cannot_use_features_until_verified(client):
    s = register(client)
    h = auth(s["access_token"])
    assert client.get(f"{API}/hydration/today", headers=h).json()["error"]["code"] == "email_not_verified"
    assert client.get(f"{API}/me", headers=h).status_code == 200  # profile still reachable

    bad = client.post(f"{API}/auth/verify-email", json={"code": "000000" if last_code(s["user"]["email"]) != "000000" else "111111"}, headers=h)
    assert bad.status_code == 400
    ok = client.post(f"{API}/auth/verify-email", json={"code": last_code(s["user"]["email"])}, headers=h)
    assert ok.status_code == 200 and ok.json()["email_verified"] is True
    assert client.get(f"{API}/hydration/today", headers=h).status_code == 200


def test_verification_code_locks_after_max_attempts(client):
    s = register(client)
    h = auth(s["access_token"])
    real = last_code("ada@example.com")
    wrong = "123456" if real != "123456" else "654321"
    for _ in range(5):
        assert client.post(f"{API}/auth/verify-email", json={"code": wrong}, headers=h).status_code == 400
    # Even the right code is refused now; a new one must be requested.
    assert client.post(f"{API}/auth/verify-email", json={"code": real}, headers=h).status_code == 400


def test_verification_code_expires(client, db_factory):
    s = register(client)
    with db_factory() as db:
        for row in db.execute(select(OneTimeCode)).scalars():
            row.expires_at = row.created_at - timedelta(seconds=1)
        db.commit()
    res = client.post(f"{API}/auth/verify-email", json={"code": last_code("ada@example.com")},
                      headers=auth(s["access_token"]))
    assert res.status_code == 400


def test_resend_has_cooldown_and_invalidates_old_code(client, db_factory):
    s = register(client)
    h = auth(s["access_token"])
    first = last_code("ada@example.com")
    assert client.post(f"{API}/auth/resend-verification", headers=h).status_code == 429
    with db_factory() as db:  # pretend the cooldown has passed
        for row in db.execute(select(OneTimeCode)).scalars():
            row.created_at -= timedelta(minutes=2)
        db.commit()
    assert client.post(f"{API}/auth/resend-verification", headers=h).status_code == 202
    second = last_code("ada@example.com")
    if first != second:
        assert client.post(f"{API}/auth/verify-email", json={"code": first}, headers=h).status_code == 400
    assert client.post(f"{API}/auth/verify-email", json={"code": second}, headers=h).status_code == 200


def test_login_success_and_uniform_failure(client):
    register(client)
    ok = client.post(f"{API}/auth/login", json={"email": "ADA@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["first_name"] == "Ada"
    wrong_pw = client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": "nope-nope-nope"})
    no_user = client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_login_is_rate_limited_per_email(client):
    register(client)
    for _ in range(10):
        client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": "wrong-password!"})
    res = client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    assert res.status_code == 429 and "Retry-After" in res.headers


def test_refresh_rotates_and_reuse_revokes_family(client):
    s = register(client)
    r1 = client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()["refresh_token"]
    assert new != s["refresh_token"]
    # Replaying the old token is treated as theft: it fails AND kills the new token.
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": new}).status_code == 401


def test_logout_revokes_refresh_token(client):
    s = register(client)
    assert client.post(f"{API}/auth/logout", json={"refresh_token": s["refresh_token"]}).status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]}).status_code == 401


def test_invalid_or_tampered_access_tokens_are_rejected(client):
    s = register(client)
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(f"{API}/me", headers=auth(s["access_token"] + "x")).status_code == 401
    assert client.get(f"{API}/me", headers=auth(s["refresh_token"])).status_code == 401


def test_forgot_password_does_not_reveal_accounts(client):
    register(client)
    a = client.post(f"{API}/auth/forgot-password", json={"email": "ada@example.com"})
    b = client.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert [m.to for m in TEST_OUTBOX].count("ada@example.com") == 2  # verification + reset
    assert not any(m.to == "ghost@example.com" for m in TEST_OUTBOX)


def test_reset_password_flow_revokes_sessions_and_old_tokens(client, db_factory):
    s = register(client)
    client.post(f"{API}/auth/forgot-password", json={"email": "ada@example.com"})
    code = last_code("ada@example.com")
    new_pw = "a-brand-new-passphrase"
    bad = client.post(f"{API}/auth/reset-password",
                      json={"email": "ada@example.com", "code": "999999" if code != "999999" else "888888", "new_password": new_pw})
    assert bad.status_code == 400
    time.sleep(1.05)  # access token must be issued in an earlier second than the password change
    ok = client.post(f"{API}/auth/reset-password", json={"email": "ada@example.com", "code": code, "new_password": new_pw})
    assert ok.status_code == 204
    assert client.post(f"{API}/auth/reset-password",
                       json={"email": "ada@example.com", "code": code, "new_password": new_pw}).status_code == 400  # single use
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]}).status_code == 401
    assert client.get(f"{API}/me", headers=auth(s["access_token"])).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
    login = client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": new_pw})
    assert login.status_code == 200 and login.json()["user"]["email_verified"] is True


def test_change_password(client, verified):
    h, s = verified
    bad = client.post(f"{API}/auth/change-password", headers=h,
                      json={"current_password": "not-my-password", "new_password": "another-good-one"})
    assert bad.status_code == 400
    time.sleep(1.05)
    ok = client.post(f"{API}/auth/change-password", headers=h,
                     json={"current_password": PASSWORD, "new_password": "another-good-one"})
    assert ok.status_code == 200
    assert client.get(f"{API}/me", headers=auth(ok.json()["access_token"])).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]}).status_code == 401
