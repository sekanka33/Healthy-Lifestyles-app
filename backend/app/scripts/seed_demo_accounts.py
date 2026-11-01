"""Create (or reset) two ready-to-use test accounts: one Free, one Premium.

    python -m app.scripts.seed_demo_accounts            # random passwords, printed once
    python -m app.scripts.seed_demo_accounts --password "my-own-password"

- Both accounts are email-verified so they can sign in straight away.
- Premium is granted as a `promotional` entitlement with no expiry — the same server-side record the
  real subscription flow writes, so every Premium check behaves exactly as for a paying user.
- Running it again resets the passwords (and re-grants Premium); data the accounts created is kept.
- Refuses to run when ENVIRONMENT=production: test accounts must never exist on a live server.
"""

import argparse
import secrets
import string
import sys
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.billing import SubscriptionEntitlement
from app.models.user import EmailPreferences, NotificationPreferences, User, UserPreferences
from app.services.hydration import set_goal

ACCOUNTS = [
    {"email": "free.demo@example.com", "first_name": "Free", "last_name": "Demo", "premium": False},
    {"email": "premium.demo@example.com", "first_name": "Premium", "last_name": "Demo", "premium": True},
]


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(3))  # e.g. aB3xQ-9kLmP-z2Rt7


def upsert(db, spec: dict, password: str, timezone: str) -> User:
    user = db.execute(select(User).where(User.email == spec["email"])).scalar_one_or_none()
    if user is None:
        user = User(id=uuid.uuid4(), email=spec["email"], password_hash=hash_password(password),
                    first_name=spec["first_name"], last_name=spec["last_name"], timezone=timezone,
                    email_verified_at=utcnow())
        db.add(user)
        db.flush()
        db.add_all([UserPreferences(user_id=user.id), NotificationPreferences(user_id=user.id),
                    EmailPreferences(user_id=user.id)])
        set_goal(db, user, 2000, commit=False)
    else:
        user.password_hash = hash_password(password)
        user.password_changed_at = utcnow().replace(microsecond=0)  # old sessions stop working
        user.email_verified_at = user.email_verified_at or utcnow()
        user.is_active = True

    ent = db.execute(select(SubscriptionEntitlement).where(
        SubscriptionEntitlement.user_id == user.id,
        SubscriptionEntitlement.entitlement == get_settings().revenuecat_premium_entitlement,
    )).scalar_one_or_none()
    if spec["premium"]:
        if ent is None:
            ent = SubscriptionEntitlement(user_id=user.id, entitlement=get_settings().revenuecat_premium_entitlement,
                                          status="active")
            db.add(ent)
        ent.status, ent.store, ent.product_id = "active", "promotional", "demo_premium"
        ent.expires_at, ent.will_renew, ent.environment = None, False, "sandbox"
        ent.current_period_start, ent.last_verified_at = utcnow(), utcnow()
    elif ent is not None:
        db.delete(ent)  # the Free account must stay Free
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--password", help="use this password for both accounts instead of random ones")
    parser.add_argument("--timezone", default="Africa/Johannesburg")
    args = parser.parse_args()

    if get_settings().environment == "production":
        print("Refusing to create test accounts in production.", file=sys.stderr)
        return 1
    if args.password and len(args.password) < 10:
        print("Password must be at least 10 characters.", file=sys.stderr)
        return 1

    rows = []
    with SessionLocal() as db:
        for spec in ACCOUNTS:
            pw = args.password or random_password()
            upsert(db, spec, pw, args.timezone)
            rows.append((spec, pw))
        db.commit()

    print("\nTest accounts ready (keep these private):\n")
    for spec, pw in rows:
        print(f"  {'Premium' if spec['premium'] else 'Free':<8} email: {spec['email']:<28} password: {pw}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
