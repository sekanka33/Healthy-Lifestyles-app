"""Admin dashboard authentication, sessions, MFA, RBAC and audit logging (Phase 3)."""

from datetime import timedelta

import pytest
from fastapi import APIRouter
from sqlalchemy import select

from app.api.admin_deps import Permission
from app.core import totp
from app.core.admin_permissions import PERMISSIONS, ROLE_PERMISSIONS, has_permission
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import utcnow
from app.main import app
from app.models.admin import AdminSession, AdminUser, AuditLog
from app.scripts.create_owner import create_owner
from tests.conftest import auth, register

ADMIN_PW = "admin-password-long-enough"
BASE = "/api/v1/admin"


def make_admin(db_factory, role="owner", email=None, password=ADMIN_PW, active=True) -> AdminUser:
    db = db_factory()
    admin = AdminUser(email=email or f"{role}@example.com", full_name=f"{role.title()} Person",
                      password_hash=hash_password(password), role=role, is_active=active)
    db.add(admin)
    db.commit()
    db.close()
    return admin


def login(client, email, password=ADMIN_PW):
    return client.post(f"{BASE}/auth/login", json={"email": email, "password": password})


def admin_headers(client, db_factory, role="owner") -> dict:
    admin = make_admin(db_factory, role=role)
    res = login(client, admin.email)
    assert res.status_code == 200, res.text
    return auth(res.json()["token"])


def audit_rows(db_factory, action=None) -> list[AuditLog]:
    db = db_factory()
    stmt = select(AuditLog).order_by(AuditLog.id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = list(db.execute(stmt).scalars())
    db.close()
    return rows


@pytest.fixture
def mfa_required(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_require_mfa", True)


@pytest.fixture
def probe_routes():
    """Temporary routes guarded by specific permissions, to test enforcement per role."""
    router = APIRouter()

    @router.get("/api/v1/admin/_probe/payments")
    def payments(_: Permission("payments.read")):
        return {"ok": True}

    @router.get("/api/v1/admin/_probe/support")
    def support(_: Permission("support.manage")):
        return {"ok": True}

    @router.get("/api/v1/admin/_probe/settings")
    def settings(_: Permission("settings.manage")):
        return {"ok": True}

    before = list(app.router.routes)
    app.include_router(router)
    yield
    app.router.routes[:] = before


# ---------- TOTP ----------

def test_totp_matches_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.code_at(secret, 2000000000 // 30) == "279037"


def test_totp_rejects_replay_and_far_drift():
    secret = totp.new_secret()
    now = 1_800_000_000.0
    step = totp.current_step(now)
    code = totp.code_at(secret, step)
    assert totp.verify(secret, code, last_step=None, now=now) == step
    assert totp.verify(secret, code, last_step=step, now=now) is None  # replay
    assert totp.verify(secret, totp.code_at(secret, step - 3), last_step=None, now=now) is None
    assert totp.verify(secret, "12345", last_step=None, now=now) is None


# ---------- Login ----------

def test_owner_login_returns_session_and_profile(client, db_factory):
    make_admin(db_factory)
    res = login(client, "OWNER@example.com")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok" and body["token"].startswith("lpa_")
    assert body["admin"]["role"] == "owner" and body["admin"]["role_label"] == "Owner"
    assert set(body["admin"]["permissions"]) == set(PERMISSIONS)
    assert "password_hash" not in body["admin"] and "mfa_secret_enc" not in body["admin"]

    me = client.get(f"{BASE}/auth/me", headers=auth(body["token"]))
    assert me.status_code == 200 and me.json()["email"] == "owner@example.com"
    assert [r.action for r in audit_rows(db_factory)] == ["admin.login"]


def test_session_token_is_stored_hashed(client, db_factory):
    make_admin(db_factory)
    token = login(client, "owner@example.com").json()["token"]
    db = db_factory()
    row = db.execute(select(AdminSession)).scalar_one()
    assert row.token_hash != token and len(row.token_hash) == 64
    db.close()


@pytest.mark.parametrize("email,password,reason", [
    ("owner@example.com", "wrong-password-123", "bad_password"),
    ("nobody@example.com", ADMIN_PW, "unknown_email"),
])
def test_failed_login_is_generic_and_audited(client, db_factory, email, password, reason):
    make_admin(db_factory)
    res = login(client, email, password)
    assert res.status_code == 401
    assert res.json()["error"] == {"code": "invalid_credentials", "message": "Email or password is incorrect."}
    rows = audit_rows(db_factory, "admin.login_failed")
    assert len(rows) == 1 and rows[0].details == {"reason": reason} and rows[0].actor_email == email


def test_inactive_admin_cannot_sign_in(client, db_factory):
    make_admin(db_factory, active=False)
    assert login(client, "owner@example.com").status_code == 401


def test_login_is_rate_limited_per_email(client, db_factory):
    make_admin(db_factory)
    for _ in range(5):
        assert login(client, "owner@example.com", "wrong-password-123").status_code == 401
    res = login(client, "owner@example.com", ADMIN_PW)
    assert res.status_code == 429 and "Retry-After" in res.headers


def test_login_validates_input(client, db_factory):
    assert client.post(f"{BASE}/auth/login", json={"email": "not-an-email", "password": "x"}).status_code == 422
    assert client.post(f"{BASE}/auth/login", json={"email": "a@b.co"}).status_code == 422


# ---------- Separation from the mobile app ----------

def test_no_token_is_rejected(client, db_factory):
    for path in ("/auth/me", "/roles"):
        res = client.get(BASE + path)
        assert res.status_code == 401 and res.json()["error"]["code"] == "admin_not_authenticated"


def test_app_user_token_cannot_reach_admin_api(client, db_factory):
    session = register(client)
    h = auth(session["access_token"])
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401
    assert client.get(f"{BASE}/roles", headers=h).status_code == 401
    # Same email and password as an app account doesn't create an admin login either.
    assert login(client, "ada@example.com", "correct-horse-battery").status_code == 401


def test_admin_token_cannot_reach_app_api(client, db_factory):
    h = admin_headers(client, db_factory)
    assert client.get("/api/v1/me", headers=h).status_code == 401


def test_garbage_and_forged_tokens_are_rejected(client, db_factory):
    for token in ("lpa_not-a-real-token", "eyJhbGciOiJub25lIn0.e30.", "x" * 500):
        assert client.get(f"{BASE}/auth/me", headers=auth(token)).status_code == 401


# ---------- Sessions ----------

def test_logout_revokes_the_session(client, db_factory):
    h = admin_headers(client, db_factory)
    assert client.post(f"{BASE}/auth/logout", headers=h).status_code == 204
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401
    assert audit_rows(db_factory, "admin.logout")


def test_idle_session_expires(client, db_factory):
    h = admin_headers(client, db_factory)
    db = db_factory()
    row = db.execute(select(AdminSession)).scalar_one()
    row.last_seen_at = utcnow() - timedelta(minutes=get_settings().admin_session_idle_minutes + 1)
    db.commit()
    db.close()
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401


def test_absolute_session_lifetime(client, db_factory):
    h = admin_headers(client, db_factory)
    db = db_factory()
    row = db.execute(select(AdminSession)).scalar_one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    db.close()
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401


def test_deactivating_an_admin_ends_their_sessions(client, db_factory):
    h = admin_headers(client, db_factory)
    db = db_factory()
    db.execute(select(AdminUser)).scalar_one().is_active = False
    db.commit()
    db.close()
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401


def test_change_password(client, db_factory):
    h = admin_headers(client, db_factory)
    wrong = client.post(f"{BASE}/auth/change-password", headers=h,
                        json={"current_password": "nope-nope-nope", "new_password": "another-long-password"})
    assert wrong.status_code == 401
    weak = client.post(f"{BASE}/auth/change-password", headers=h,
                       json={"current_password": ADMIN_PW, "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"

    ok = client.post(f"{BASE}/auth/change-password", headers=h,
                     json={"current_password": ADMIN_PW, "new_password": "another-long-password"})
    assert ok.status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401  # old session is dead
    assert client.get(f"{BASE}/auth/me", headers=auth(ok.json()["token"])).status_code == 200
    assert login(client, "owner@example.com", "another-long-password").status_code == 200
    rows = audit_rows(db_factory, "admin.password_changed")
    assert len(rows) == 1 and rows[0].details == {}


# ---------- Role-based access ----------

def test_permission_matrix_is_closed():
    for role, perms in ROLE_PERMISSIONS.items():
        assert perms <= set(PERMISSIONS), role
    assert ROLE_PERMISSIONS["owner"] == frozenset(PERMISSIONS)
    with pytest.raises(ValueError):
        has_permission("owner", "payments.reed")


def test_role_boundaries_from_the_spec():
    assert not has_permission("support", "payments.read")  # support can't see finance
    assert has_permission("finance", "payments.read")
    assert not has_permission("finance", "users.read")
    assert not has_permission("admin", "admins.manage")  # owner-only
    assert not has_permission("admin", "settings.manage")
    assert not has_permission("admin", "users.delete")
    assert has_permission("technical", "system.read") and not has_permission("technical", "users.read")


@pytest.mark.parametrize("role,payments,support,settings", [
    ("owner", 200, 200, 200),
    ("admin", 403, 200, 403),
    ("support", 403, 200, 403),
    ("finance", 200, 403, 403),
    ("technical", 403, 403, 403),
])
def test_permissions_are_enforced_on_the_backend(client, db_factory, probe_routes, role, payments, support, settings):
    h = admin_headers(client, db_factory, role)
    assert client.get(f"{BASE}/_probe/payments", headers=h).status_code == payments
    assert client.get(f"{BASE}/_probe/support", headers=h).status_code == support
    res = client.get(f"{BASE}/_probe/settings", headers=h)
    assert res.status_code == settings
    if settings == 403:
        assert res.json()["error"]["code"] == "forbidden"


def test_roles_endpoint_is_owner_only(client, db_factory):
    owner = admin_headers(client, db_factory, "owner")
    res = client.get(f"{BASE}/roles", headers=owner)
    assert res.status_code == 200
    assert {r["key"] for r in res.json()["roles"]} == set(ROLE_PERMISSIONS)

    admin = make_admin(db_factory, "admin")
    h = auth(login(client, admin.email).json()["token"])
    assert client.get(f"{BASE}/roles", headers=h).status_code == 403


# ---------- MFA ----------

def _enrol(client, h) -> str:
    setup = client.post(f"{BASE}/auth/mfa/setup", headers=h)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    res = client.post(f"{BASE}/auth/mfa/enable", headers=h, json={"code": totp.code_at(secret, totp.current_step())})
    assert res.status_code == 200, res.text
    assert res.json()["mfa_enabled"] is True
    return secret


def test_mfa_enrolment_and_login(client, db_factory):
    h = admin_headers(client, db_factory)
    other = auth(login(client, "owner@example.com").json()["token"])
    secret = _enrol(client, h)
    assert client.get(f"{BASE}/auth/me", headers=other).status_code == 401  # pre-MFA sessions ended

    db = db_factory()
    stored = db.execute(select(AdminUser)).scalar_one().mfa_secret_enc
    assert stored and secret not in stored  # encrypted at rest
    db.close()

    step1 = login(client, "owner@example.com")
    assert step1.status_code == 200 and step1.json()["status"] == "mfa_required"
    assert "token" not in step1.json()
    mfa_token = step1.json()["mfa_token"]
    # The challenge isn't a session.
    assert client.get(f"{BASE}/auth/me", headers=auth(mfa_token)).status_code == 401

    bad = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_mfa_code"

    # The enrolment code's step is burned; the next step is still inside the drift window.
    code = totp.code_at(secret, totp.current_step() + 1)
    ok = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code})
    assert ok.status_code == 200 and ok.json()["admin"]["mfa_enabled"] is True
    replay = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code})
    assert replay.status_code == 401

    actions = [r.action for r in audit_rows(db_factory)]
    assert "admin.mfa_enabled" in actions and actions.count("admin.login") == 3


def test_mfa_challenge_dies_after_password_change(client, db_factory):
    h = admin_headers(client, db_factory)
    secret = _enrol(client, h)
    challenge = login(client, "owner@example.com").json()["mfa_token"]
    client.post(f"{BASE}/auth/change-password", headers=h,
                json={"current_password": ADMIN_PW, "new_password": "another-long-password"})
    res = client.post(f"{BASE}/auth/mfa/verify",
                      json={"mfa_token": challenge, "code": totp.code_at(secret, totp.current_step() + 1)})
    assert res.status_code == 401 and res.json()["error"]["code"] == "mfa_challenge_expired"


def test_mfa_required_blocks_everything_but_enrolment(client, db_factory, probe_routes, mfa_required):
    h = admin_headers(client, db_factory)
    me = client.get(f"{BASE}/auth/me", headers=h).json()
    assert me["mfa_required"] is True and me["mfa_setup_needed"] is True
    res = client.get(f"{BASE}/_probe/payments", headers=h)
    assert res.status_code == 403 and res.json()["error"]["code"] == "mfa_setup_required"

    _enrol(client, h)
    assert client.get(f"{BASE}/_probe/payments", headers=h).status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=h).json()["mfa_setup_needed"] is False
    # Can't be switched off while required.
    off = client.post(f"{BASE}/auth/mfa/disable", headers=h, json={"password": ADMIN_PW, "code": "123456"})
    assert off.status_code == 409


def test_mfa_can_be_disabled_with_password_and_code(client, db_factory):
    h = admin_headers(client, db_factory)
    secret = _enrol(client, h)
    bad = client.post(f"{BASE}/auth/mfa/disable", headers=h,
                      json={"password": "wrong-password-1", "code": totp.code_at(secret, totp.current_step() + 1)})
    assert bad.status_code == 401
    ok = client.post(f"{BASE}/auth/mfa/disable", headers=h,
                     json={"password": ADMIN_PW, "code": totp.code_at(secret, totp.current_step() + 1)})
    assert ok.status_code == 200 and ok.json()["mfa_enabled"] is False
    assert login(client, "owner@example.com").json()["status"] == "ok"
    assert audit_rows(db_factory, "admin.mfa_disabled")


def test_production_refuses_optional_mfa(monkeypatch):
    s = get_settings().model_copy(update={"environment": "production", "admin_require_mfa": False})
    with pytest.raises(RuntimeError, match="ADMIN_REQUIRE_MFA"):
        s.validate_production()
    assert s.model_copy(update={"admin_require_mfa": None}).admin_mfa_required is True


# ---------- Owner bootstrap ----------

def test_create_owner_script(db_factory):
    db = db_factory()
    owner = create_owner(db, email=" Boss@LifePulse.app ", name="The Boss", password="a-very-long-password")
    assert owner.email == "boss@lifepulse.app" and owner.role == "owner"
    assert owner.password_hash.startswith("$argon2id$")
    with pytest.raises(ValueError, match="already exists"):
        create_owner(db, email="second@lifepulse.app", name="Second", password="a-very-long-password")
    row = db.execute(select(AuditLog).where(AuditLog.action == "admin.created")).scalar_one()
    assert row.details == {"role": "owner", "email": "boss@lifepulse.app", "via": "create_owner"}
    db.close()


@pytest.mark.parametrize("email,name,password,msg", [
    ("not-an-email", "X", "a-very-long-password", "valid email"),
    ("a@b.co", " ", "a-very-long-password", "Name"),
    ("a@b.co", "X", "short", "12 characters"),
])
def test_create_owner_validates(db_factory, email, name, password, msg):
    db = db_factory()
    with pytest.raises(ValueError, match=msg):
        create_owner(db, email=email, name=name, password=password)
    assert db.execute(select(AdminUser)).first() is None
    db.close()
