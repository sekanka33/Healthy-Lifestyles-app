"""Reports, background jobs, email delivery tracking, unsubscribe and privacy."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

import app.services.notifications  # noqa: F401  (registers job handlers)
from app.core.config import get_settings
from app.models.billing import EmailMessage, Job, SubscriptionEntitlement
from app.models.user import EmailPreferences, OneTimeCode, User
from app.services import jobs, reports
from app.services.email import TEST_OUTBOX
from app.services.email_links import unsubscribe_url
from app.services.notifications import maintenance, schedule_due_reports
from tests.conftest import PASSWORD

API = "/api/v1"
JHB = ZoneInfo("Africa/Johannesburg")


def run_jobs(db_factory) -> int:
    with db_factory() as db:
        return jobs.run_due(db)


def uid_of(s) -> uuid.UUID:
    return uuid.UUID(s["user"]["id"])


def make_premium(db_factory, s):
    with db_factory() as db:
        db.add(SubscriptionEntitlement(user_id=uid_of(s), status="active", expires_at=None))
        db.commit()


# ---------------------------------------------------------------- jobs

def test_job_queue_idempotency_retry_and_dead(db_factory):
    calls = {"n": 0}

    @jobs.handler("flaky")
    def flaky(db, payload):
        calls["n"] += 1
        raise RuntimeError("boom")

    with db_factory() as db:
        a = jobs.enqueue(db, "flaky", {}, idempotency_key="k1", max_attempts=2)
        b = jobs.enqueue(db, "flaky", {}, idempotency_key="k1")
        assert a.id == b.id
        assert jobs.run_due(db) == 1
        job = db.get(Job, a.id)
        assert job.status == "queued" and job.attempts == 1 and job.last_error.startswith("RuntimeError")
        job.run_after = datetime.now(timezone.utc) - timedelta(seconds=1)  # skip the backoff wait
        db.commit()
        jobs.run_due(db)
        assert db.get(Job, a.id).status == "dead" and calls["n"] == 2


def test_permanent_errors_and_unknown_kinds_are_not_retried(db_factory):
    with db_factory() as db:
        j = jobs.enqueue(db, "does_not_exist", {})
        jobs.run_due(db)
        assert db.get(Job, j.id).status == "dead" and db.get(Job, j.id).attempts == 1
        j2 = jobs.enqueue(db, "email_report", {"user_id": str(uuid.uuid4()), "kind": "water",
                                               "first": "2026-01-01", "last": "2026-01-01", "key": "x"})
        jobs.run_due(db)
        assert db.get(Job, j2.id).status == "dead" and "no longer exists" in db.get(Job, j2.id).last_error


def test_stale_running_jobs_are_released(db_factory):
    with db_factory() as db:
        j = jobs.enqueue(db, "noop", {})
        j.status, j.locked_at = "running", datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        assert jobs.release_stale(db) == 1 and db.get(Job, j.id).status == "queued"


# ---------------------------------------------------------------- reports

def test_previous_periods():
    wed = date(2026, 11, 4)
    assert reports.previous_period(wed, "daily") == (date(2026, 11, 3), date(2026, 11, 3))
    assert reports.previous_period(wed, "weekly") == (date(2026, 10, 26), date(2026, 11, 1))
    assert reports.previous_period(date(2026, 3, 1), "monthly") == (date(2026, 2, 1), date(2026, 2, 28))


def test_water_pdf_download_and_premium_gating(client, verified):
    h, _ = verified
    client.post(f"{API}/hydration/entries", headers=h, json={"client_id": str(uuid.uuid4()), "volume_ml": 500})
    r = client.get(f"{API}/reports/water.pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    assert client.get(f"{API}/reports/fitness.pdf", headers=h).status_code == 402
    assert client.get(f"{API}/reports/medication.pdf", headers=h).status_code == 402
    assert client.get(f"{API}/reports/water.pdf").status_code == 401


def test_email_report_on_request_with_pdf(client, verified, db_factory):
    h, s = verified
    client.post(f"{API}/hydration/entries", headers=h, json={"client_id": str(uuid.uuid4()), "volume_ml": 750})
    TEST_OUTBOX.clear()
    assert client.post(f"{API}/reports/water/email", headers=h).json()["status"] == "queued"
    client.post(f"{API}/reports/water/email", headers=h)  # double tap within 5 min: still one email
    run_jobs(db_factory)
    assert len(TEST_OUTBOX) == 1
    msg = TEST_OUTBOX[0]
    assert msg.to == "ada@example.com" and "water report" in msg.subject.lower()
    assert msg.attachments[0].content_type == "application/pdf" and msg.attachments[0].data.startswith(b"%PDF")
    assert "Unsubscribe" not in msg.text  # on-demand emails aren't marketing
    with db_factory() as db:
        assert db.execute(select(EmailMessage).where(EmailMessage.template == "report_water")).scalar_one().status == "accepted"


def _add_med_with_dose(client, h, db_factory):
    from app.models.medication import Medication

    m = client.post(f"{API}/medications", headers=h, json={
        "name": "SecretMedName", "dosage_instructions": "1 tablet", "schedule_type": "daily", "times": ["00:01"]}).json()
    with db_factory() as db:
        row = db.get(Medication, uuid.UUID(m["id"]))
        row.start_date -= timedelta(days=10)
        db.commit()
    return m


def test_medication_email_hides_details_unless_user_opts_in(client, verified, db_factory):
    h, s = verified
    make_premium(db_factory, s)
    _add_med_with_dose(client, h, db_factory)
    TEST_OUTBOX.clear()
    client.post(f"{API}/reports/medication/email", headers=h, params={"period": "weekly"})
    run_jobs(db_factory)
    summary = TEST_OUTBOX[-1]
    assert "SecretMedName" not in summary.text and "SecretMedName" not in summary.subject
    assert summary.attachments == ()  # no PDF with names by default
    client.patch(f"{API}/me/email-preferences", headers=h, json={"medication_report_detail": "detailed"})
    client.post(f"{API}/reports/medication/email", headers=h, params={"period": "this_week"})
    run_jobs(db_factory)
    detailed = TEST_OUTBOX[-1]
    assert "SecretMedName" in detailed.text and detailed.attachments


# ---------------------------------------------------------------- scheduler

def _at_local(d: date, hour: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=JHB).astimezone(timezone.utc)


def test_scheduler_sends_weekly_report_on_monday_morning_once(client, verified, db_factory):
    h, s = verified
    client.patch(f"{API}/me/email-preferences", headers=h, json={"water_summary": "weekly"})
    monday = date(2026, 11, 2)
    with db_factory() as db:
        assert schedule_due_reports(db, _at_local(monday, 6)) == 0  # before 07:00 local
        assert schedule_due_reports(db, _at_local(monday + timedelta(days=1), 9)) == 0  # not Monday
        assert schedule_due_reports(db, _at_local(monday, 7)) == 1
        schedule_due_reports(db, _at_local(monday, 8))  # an hour later: same idempotency key
        rows = db.execute(select(Job).where(Job.kind == "email_report")).scalars().all()
    assert len(rows) == 1 and rows[0].payload["first"] == "2026-10-26" and rows[0].payload["last"] == "2026-11-01"


def test_scheduled_report_skips_empty_and_turned_off(client, verified, db_factory):
    h, s = verified
    client.patch(f"{API}/me/email-preferences", headers=h, json={"water_summary": "daily"})
    TEST_OUTBOX.clear()
    with db_factory() as db:
        schedule_due_reports(db, _at_local(datetime.now(JHB).date(), 12))
    run_jobs(db_factory)
    assert TEST_OUTBOX == []  # nothing logged yesterday → no "empty" email
    # Queue one, then the user turns the emails off before it runs.
    with db_factory() as db:
        jobs.enqueue(db, "email_report", {"user_id": s["user"]["id"], "kind": "water", "first": "2026-10-01",
                                          "last": "2026-10-01", "scheduled": True, "key": "late"})
    client.patch(f"{API}/me/email-preferences", headers=h, json={"water_summary": "off"})
    run_jobs(db_factory)
    assert TEST_OUTBOX == []


def test_scheduled_email_has_list_unsubscribe(client, verified, db_factory):
    h, s = verified
    client.post(f"{API}/hydration/entries", headers=h, json={
        "client_id": str(uuid.uuid4()), "volume_ml": 300,
        "consumed_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
    client.patch(f"{API}/me/email-preferences", headers=h, json={"water_summary": "daily"})
    TEST_OUTBOX.clear()
    with db_factory() as db:
        schedule_due_reports(db, _at_local(datetime.now(JHB).date(), 23))
    run_jobs(db_factory)
    msg = TEST_OUTBOX[-1]
    assert "List-Unsubscribe" in msg.headers and msg.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/api/v1/email/unsubscribe?" in msg.text


# ---------------------------------------------------------------- unsubscribe

def test_unsubscribe_links(client, verified, db_factory):
    h, s = verified
    client.patch(f"{API}/me/email-preferences", headers=h, json={"water_summary": "weekly", "fitness_report": "weekly"})
    url = unsubscribe_url(uid_of(s), "water")
    assert url.startswith(get_settings().public_api_url)
    path = url.split("8000", 1)[1] if "8000" in url else url
    assert client.get(path).status_code == 200
    assert client.get(f"{API}/me/email-preferences", headers=h).json()["water_summary"] == "off"
    tampered = unsubscribe_url(uid_of(s), "fitness")[:-4] + "0000"
    assert client.get(tampered.split("8000", 1)[1]).status_code == 400
    assert client.get(f"{API}/me/email-preferences", headers=h).json()["fitness_report"] == "weekly"
    one_click = unsubscribe_url(uid_of(s), "fitness").split("8000", 1)[1]
    assert client.post(one_click).json() == {"status": "unsubscribed"}


# ---------------------------------------------------------------- delivery webhook

SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret-32-bytes!!!!").decode()


def signed(body: dict, *, ts: int | None = None, msg_id: str = "msg_1", secret: str = SECRET):
    raw = json.dumps(body).encode()
    ts = ts or int(time.time())
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    return raw, {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}", "content-type": "application/json"}


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_webhook_secret", SECRET)


def test_resend_webhook_marks_delivered_and_rejects_forgeries(client, verified, db_factory, webhook_secret):
    with db_factory() as db:
        db.add(EmailMessage(to_email="a@x.com", template="t", subject="s", idempotency_key="ik",
                            status="accepted", provider_message_id="re_123"))
        db.commit()
    body = {"type": "email.delivered", "data": {"email_id": "re_123"}}
    raw, headers = signed(body)
    assert client.post(f"{API}/email/webhooks/resend", content=raw, headers=headers).json()["status"] == "processed"
    assert client.post(f"{API}/email/webhooks/resend", content=raw, headers=headers).json()["status"] == "duplicate"
    with db_factory() as db:
        m = db.execute(select(EmailMessage).where(EmailMessage.provider_message_id == "re_123")).scalar_one()
        assert m.status == "delivered" and m.delivered_at is not None
    bad_raw, bad_headers = signed(body, msg_id="msg_2", secret="whsec_" + base64.b64encode(b"x" * 32).decode())
    assert client.post(f"{API}/email/webhooks/resend", content=bad_raw, headers=bad_headers).status_code == 401
    old_raw, old_headers = signed(body, msg_id="msg_3", ts=int(time.time()) - 3600)
    assert client.post(f"{API}/email/webhooks/resend", content=old_raw, headers=old_headers).status_code == 401  # replay
    tampered_headers = {**headers, "svix-id": "msg_4"}
    assert client.post(f"{API}/email/webhooks/resend", content=raw, headers=tampered_headers).status_code == 401


# ---------------------------------------------------------------- privacy

def test_export_contains_my_data_but_no_secrets(client, verified):
    h, _ = verified
    client.post(f"{API}/hydration/entries", headers=h, json={"client_id": str(uuid.uuid4()), "volume_ml": 333})
    r = client.get(f"{API}/me/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["account"]["email"] == "ada@example.com"
    assert [e["volume_ml"] for e in data["hydration_entries"]] == [333]
    text = r.text
    for secret in ("password_hash", "argon2", "token_hash", "code_hash", "refresh_token_enc"):
        assert secret not in text


def test_export_by_email(client, verified, db_factory):
    h, _ = verified
    TEST_OUTBOX.clear()
    assert client.post(f"{API}/me/export/email", headers=h).status_code == 202
    run_jobs(db_factory)
    att = TEST_OUTBOX[-1].attachments[0]
    assert att.content_type == "application/json" and json.loads(att.data)["account"]["email"] == "ada@example.com"


def test_delete_account_requires_password_and_erases_everything(client, verified, db_factory):
    h, s = verified
    client.post(f"{API}/hydration/entries", headers=h, json={"client_id": str(uuid.uuid4()), "volume_ml": 250})
    assert client.post(f"{API}/me/delete", headers=h, json={"password": "wrong-password"}).status_code == 400
    TEST_OUTBOX.clear()
    assert client.post(f"{API}/me/delete", headers=h, json={"password": PASSWORD}).status_code == 204
    with db_factory() as db:
        assert db.get(User, uid_of(s)) is None
        assert db.get(EmailPreferences, uid_of(s)) is None
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
    assert "deleted" in TEST_OUTBOX[-1].subject and "cancel" in TEST_OUTBOX[-1].text


# ---------------------------------------------------------------- receipts & maintenance

def test_purchase_webhook_emails_a_receipt(client, verified, db_factory, monkeypatch):
    from tests.test_billing import FakeRevenueCat, SECRET as RC_SECRET, event, hook, subscriber
    from app.services import revenuecat

    fake = FakeRevenueCat()
    monkeypatch.setattr(revenuecat, "get_client", lambda: fake)
    monkeypatch.setattr(get_settings(), "revenuecat_webhook_auth", RC_SECRET)
    h, s = verified
    fake.subscribers[s["user"]["id"]] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    hook(client, event(s["user"]["id"]))
    hook(client, event(s["user"]["id"]))  # duplicate event id differs, same transaction id: still one receipt
    TEST_OUTBOX.clear()
    run_jobs(db_factory)
    receipts = [m for m in TEST_OUTBOX if "receipt" in m.subject.lower()]
    assert len(receipts) == 1 and receipts[0].attachments[0].data.startswith(b"%PDF")


def test_maintenance_removes_expired_security_records(client, verified, db_factory):
    with db_factory() as db:
        for code in db.execute(select(OneTimeCode)).scalars():
            code.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
        maintenance(db)
        assert db.execute(select(OneTimeCode)).scalars().all() == []
