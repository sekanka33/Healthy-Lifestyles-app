import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DB, AnyUser
from app.core import rate_limit, security
from app.core.config import get_settings
from app.services import email as email_svc
from app.services import jobs, privacy

router = APIRouter(prefix="/me", tags=["privacy"])


@router.get("/export")
def export(user: AnyUser, db: DB):
    """Everything we hold about you, as JSON (no passwords, tokens or codes). Works on any plan."""
    rate_limit.hit(db, f"export:user:{user.id}", limit=5, window_seconds=3600)
    return Response(privacy.export_bytes(db, user), media_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="healthy-lifestyles-export.json"', "Cache-Control": "private, no-store"})


@router.post("/export/email", status_code=status.HTTP_202_ACCEPTED)
def export_by_email(user: AnyUser, db: DB):
    """Emails the export to the account's verified address (sent by the worker)."""
    if user.email_verified_at is None:
        raise HTTPException(403, {"code": "email_not_verified", "message": "Verify your email first."})
    rate_limit.hit(db, f"export-email:user:{user.id}", limit=3, window_seconds=86400)
    key = f"{user.id}:{int(time.time() // 600)}"
    jobs.enqueue(db, "email_export", {"user_id": str(user.id), "key": key}, idempotency_key=f"export:{key}")
    return {"status": "queued", "to": user.email}


class DeleteIn(BaseModel):
    password: str = Field(max_length=128)


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(data: DeleteIn, user: AnyUser, db: DB, background: BackgroundTasks):
    """Permanently deletes the account and all its data. Requires the current password."""
    rate_limit.hit(db, f"delete:user:{user.id}", limit=5, window_seconds=3600)
    if not security.verify_password(data.password, user.password_hash):
        raise HTTPException(400, {"code": "invalid_password", "message": "Password is incorrect."})
    email, name = user.email, user.first_name
    privacy.delete_account(db, user)
    s = get_settings()
    background.add_task(email_svc.get_provider().send, email_svc.OutgoingEmail(
        to=email, subject=f"Your {s.app_name} account was deleted",
        text=(f"Hi {name},\n\nYour {s.app_name} account and its data have been deleted.\n"
              "If you subscribed to Premium, also cancel it in your App Store or Google Play account settings — "
              "the store bills you, so we can't cancel it for you.\n\n— " + s.app_name)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
