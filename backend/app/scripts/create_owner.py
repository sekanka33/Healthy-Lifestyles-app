"""Create the first Owner account for the admin dashboard.

    python -m app.scripts.create_owner --email you@yourdomain.com --name "Your Name"

- The password is typed at a hidden prompt (twice), never passed on the command line, so it can't
  leak into shell history or process listings. For automation, ADMIN_OWNER_PASSWORD may be set instead.
- Refuses to run if an Owner already exists. Further admins are added from the dashboard (Phase 10).
- After signing in, turn on two-step verification (it's required when ENVIRONMENT=production).
"""

import argparse
import getpass
import os
import sys

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from pydantic import EmailStr
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin import AdminUser
from app.schemas.auth import PASSWORD_MAX
from app.services import admin_auth, audit


def read_password() -> str:
    env = os.environ.get("ADMIN_OWNER_PASSWORD")
    if env:
        return env
    if not sys.stdin.isatty():
        sys.exit("No terminal for the password prompt. Run interactively or set ADMIN_OWNER_PASSWORD.")
    first = getpass.getpass("Password (min 12 characters): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        sys.exit("Passwords don't match.")
    return first


def create_owner(db, *, email: str, name: str, password: str) -> AdminUser:
    email = admin_auth.normalise_email(email)
    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValidationError:
        raise ValueError("That isn't a valid email address.") from None
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Name must be 1-200 characters.")
    if len(password) > PASSWORD_MAX:
        raise ValueError(f"Password must be at most {PASSWORD_MAX} characters.")
    try:
        admin_auth.validate_new_password(password, email=email)
    except HTTPException as exc:
        raise ValueError(exc.detail["message"]) from None
    if db.execute(select(AdminUser.id).where(AdminUser.role == "owner")).first():
        raise ValueError("An Owner account already exists.")
    if db.execute(select(AdminUser.id).where(AdminUser.email == email)).first():
        raise ValueError("An admin with that email already exists.")

    owner = AdminUser(email=email, full_name=name, password_hash=hash_password(password), role="owner")
    db.add(owner)
    db.flush()
    audit.record(db, "admin.created", actor_email="cli", resource_type="admin_user", resource_id=owner.id,
                 details={"role": "owner", "email": email, "via": "create_owner"}, commit=False)
    db.commit()
    return owner


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin dashboard Owner.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        owner = create_owner(db, email=args.email, name=args.name, password=read_password())
    except ValueError as exc:
        sys.exit(f"Not created: {exc}")
    finally:
        db.close()
    print(f"Owner created: {owner.email}. Sign in to the admin dashboard and turn on two-step verification.")


if __name__ == "__main__":
    main()
