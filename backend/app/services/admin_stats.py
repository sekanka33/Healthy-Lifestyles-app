"""Aggregate business statistics for the admin overview. Everything is computed from real rows.

Definitions (also shown in the dashboard tooltips):
- Premium user: has the premium entitlement now (active / grace period / cancelled-but-paid-up, not
  past expiry). Same rule as the app's `is_premium`. Promotional grants are counted and reported apart.
- Converted user: has at least one verified production payment (succeeded or later refunded).
- Conversion rate: converted users / registered users.
- Revenue: verified production payments with status `succeeded`, grouped by currency (never summed
  across currencies). Sandbox purchases and refunds are excluded.
- MRR: for auto-renewing paid production subscriptions, the latest succeeded payment normalised to a
  30.44-day month by its billing period, per currency.
- Cancellations / failed payments: RevenueCat CANCELLATION / BILLING_ISSUE webhook events (production).
- Active user: made at least one authenticated app request that day (tracked from `user_activity_days`).
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Date, and_, cast, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.admin import AuditLog
from app.models.analytics import UserActivityDay
from app.models.billing import PaymentTransaction, SubscriptionEntitlement, WebhookEvent
from app.models.fitness import Workout
from app.models.hydration import HydrationEntry
from app.models.medication import Medication, MedicationDose
from app.models.user import User
from app.services.entitlements import ACTIVE_STATUSES

MAX_RANGE_DAYS = 366
MONTH_DAYS = Decimal("30.4375")
PAID_STATUSES = ("succeeded", "refunded")


@dataclass(frozen=True)
class Range:
    start: date  # inclusive, UTC
    end: date  # inclusive, UTC

    @property
    def lo(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=timezone.utc)

    @property
    def hi(self) -> datetime:  # exclusive
        return datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=timezone.utc)

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]


def parse_range(start: date | None, end: date | None) -> Range:
    """Validate a dashboard date range. Raises ValueError with a user-facing message."""
    today = utcnow().date()
    end = end or today
    start = start or end - timedelta(days=29)
    if start > end:
        raise ValueError("The start date must be on or before the end date.")
    if end > today:
        raise ValueError("The end date cannot be in the future.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Choose a range of at most {MAX_RANGE_DAYS} days.")
    return Range(start, end)


# ---------- dialect helpers (PostgreSQL in production, SQLite in tests) ----------

def _is_pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _day(db: Session, col):
    return cast(func.timezone("UTC", col), Date) if _is_pg(db) else func.date(col)


def _month(db: Session, col):
    return func.to_char(func.timezone("UTC", col), "YYYY-MM") if _is_pg(db) else func.strftime("%Y-%m", col)


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _money(v: Decimal | None) -> str:
    return str((v or Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------- users ----------

def _premium_filter(now: datetime):
    return and_(
        SubscriptionEntitlement.entitlement == get_settings().revenuecat_premium_entitlement,
        SubscriptionEntitlement.status.in_(ACTIVE_STATUSES),
        or_(SubscriptionEntitlement.expires_at.is_(None), SubscriptionEntitlement.expires_at > now),
    )


def user_stats(db: Session, r: Range) -> dict:
    now = utcnow()
    total = db.scalar(select(func.count()).select_from(User)) or 0
    new_in_range = db.scalar(select(func.count()).select_from(User).where(User.created_at >= r.lo, User.created_at < r.hi)) or 0
    month_start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=timezone.utc)
    new_this_month = db.scalar(select(func.count()).select_from(User).where(User.created_at >= month_start)) or 0

    premium_rows = db.execute(
        select(SubscriptionEntitlement.store, func.count(distinct(SubscriptionEntitlement.user_id)))
        .where(_premium_filter(now)).group_by(SubscriptionEntitlement.store)
    ).all()
    premium = sum(n for _, n in premium_rows)
    promotional = sum(n for store, n in premium_rows if store == "promotional")

    active = db.scalar(select(func.count(distinct(UserActivityDay.user_id)))
                       .where(UserActivityDay.day >= r.start, UserActivityDay.day <= r.end)) or 0
    tracking_since = db.scalar(select(func.min(UserActivityDay.day)))

    return {
        "total": total,
        "active_in_range": active,
        "activity_tracked_since": tracking_since,
        "new_in_range": new_in_range,
        "new_this_month": new_this_month,
        "premium": premium,
        "premium_promotional": promotional,
        "free": max(total - premium, 0),
    }


def _converted_users(db: Session, before: datetime | None = None) -> int:
    stmt = select(func.count(distinct(PaymentTransaction.user_id))).where(
        PaymentTransaction.status.in_(PAID_STATUSES), PaymentTransaction.environment == "production")
    if before is not None:
        stmt = stmt.where(PaymentTransaction.purchased_at < before)
    return db.scalar(stmt) or 0


def _webhook_counts(db: Session, r: Range) -> dict[str, int]:
    rows = db.execute(
        select(WebhookEvent.event_type, WebhookEvent.summary).where(
            WebhookEvent.provider == "revenuecat",
            WebhookEvent.event_type.in_(("CANCELLATION", "BILLING_ISSUE")),
            WebhookEvent.received_at >= r.lo, WebhookEvent.received_at < r.hi,
        )
    ).all()
    counts = {"CANCELLATION": 0, "BILLING_ISSUE": 0}
    for event_type, summary in rows:
        if str((summary or {}).get("environment") or "").upper() == "SANDBOX":
            continue
        counts[event_type] += 1
    return counts


def subscription_stats(db: Session, r: Range, users: dict) -> dict:
    converted = _converted_users(db)
    hooks = _webhook_counts(db, r)
    return {
        "premium_active": users["premium"],
        "converted_users": converted,
        "conversion_rate": round(converted / users["total"], 4) if users["total"] else None,
        "cancellations_in_range": hooks["CANCELLATION"],
        "failed_payments_in_range": hooks["BILLING_ISSUE"],
    }


# ---------- revenue ----------

def _paid_production():
    return and_(PaymentTransaction.status == "succeeded", PaymentTransaction.environment == "production",
                PaymentTransaction.amount.is_not(None), PaymentTransaction.currency.is_not(None))


def _mrr(db: Session) -> dict[str, Decimal]:
    now = utcnow()
    subs = db.execute(
        select(SubscriptionEntitlement.user_id, SubscriptionEntitlement.product_id).where(
            _premium_filter(now), SubscriptionEntitlement.will_renew.is_(True),
            SubscriptionEntitlement.environment == "production", SubscriptionEntitlement.store != "promotional",
        )
    ).all()
    if not subs:
        return {}
    txns = db.execute(
        select(PaymentTransaction).where(_paid_production(), PaymentTransaction.user_id.in_([u for u, _ in subs]))
        .order_by(PaymentTransaction.purchased_at.desc())
    ).scalars()
    latest: dict = {}
    for t in txns:
        latest.setdefault(t.user_id, t)
    mrr: dict[str, Decimal] = defaultdict(Decimal)
    for t in latest.values():
        amount = Decimal(t.amount)
        if t.period_start and t.period_end:
            days = Decimal((as_utc(t.period_end) - as_utc(t.period_start)).total_seconds()) / Decimal(86400)
            if days >= 1:
                amount = amount * MONTH_DAYS / days
        mrr[t.currency] += amount
    return mrr


def revenue_stats(db: Session, r: Range) -> dict:
    def by_currency(*conds):
        return {c: a for c, a in db.execute(
            select(PaymentTransaction.currency, func.sum(PaymentTransaction.amount))
            .where(_paid_production(), *conds).group_by(PaymentTransaction.currency)).all()}

    all_time = by_currency()
    in_range = by_currency(PaymentTransaction.purchased_at >= r.lo, PaymentTransaction.purchased_at < r.hi)
    mrr = _mrr(db)
    currencies = sorted(set(all_time) | set(mrr))
    sandbox = db.scalar(select(func.count()).select_from(PaymentTransaction)
                        .where(PaymentTransaction.environment == "sandbox")) or 0
    return {
        "by_currency": [
            {"currency": c, "total": _money(all_time.get(c)), "in_range": _money(in_range.get(c)), "mrr": _money(mrr.get(c))}
            for c in currencies
        ],
        "sandbox_transactions_excluded": sandbox,
    }


# ---------- series ----------

def _last_months(n: int) -> list[str]:
    today = utcnow().date()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def user_growth(db: Session, r: Range) -> list[dict]:
    before = db.scalar(select(func.count()).select_from(User).where(User.created_at < r.lo)) or 0
    bucket = _day(db, User.created_at)
    per_day = {_as_date(d): n for d, n in db.execute(
        select(bucket, func.count()).where(User.created_at >= r.lo, User.created_at < r.hi).group_by(bucket)).all()}
    out, running = [], before
    for d in r.days():
        running += per_day.get(d, 0)
        out.append({"date": d.isoformat(), "new_users": per_day.get(d, 0), "total_users": running})
    return out


def active_users_daily(db: Session, r: Range) -> list[dict]:
    per_day = {_as_date(d): n for d, n in db.execute(
        select(UserActivityDay.day, func.count()).where(UserActivityDay.day >= r.start, UserActivityDay.day <= r.end)
        .group_by(UserActivityDay.day)).all()}
    return [{"date": d.isoformat(), "active_users": per_day.get(d, 0)} for d in r.days()]


def revenue_monthly(db: Session, months: int = 12) -> list[dict]:
    keys = _last_months(months)
    first = datetime.fromisoformat(keys[0] + "-01").replace(tzinfo=timezone.utc)
    bucket = _month(db, PaymentTransaction.purchased_at)
    rows = db.execute(
        select(bucket, PaymentTransaction.currency, func.sum(PaymentTransaction.amount))
        .where(_paid_production(), PaymentTransaction.purchased_at >= first)
        .group_by(bucket, PaymentTransaction.currency)
    ).all()
    sums = {(str(m), c): a for m, c, a in rows}
    currencies = sorted({c for _, c in sums})
    return [{"month": k, "amounts": {c: _money(sums.get((k, c))) for c in currencies}} for k in keys]


def conversion_monthly(db: Session, months: int = 12) -> list[dict]:
    out = []
    for k in _last_months(months):
        y, m = map(int, k.split("-"))
        end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
        users = db.scalar(select(func.count()).select_from(User).where(User.created_at < end)) or 0
        conv = _converted_users(db, before=end)
        out.append({"month": k, "registered_users": users, "converted_users": conv,
                    "rate": round(conv / users, 4) if users else None})
    return out


def feature_usage(db: Session, r: Range) -> list[dict]:
    """Distinct users and record counts per feature in the range. Counts only — no health content."""
    water = db.execute(select(func.count(distinct(HydrationEntry.user_id)), func.count()).where(
        HydrationEntry.deleted_at.is_(None), HydrationEntry.consumed_at >= r.lo, HydrationEntry.consumed_at < r.hi)).one()
    meds = db.execute(select(func.count(distinct(MedicationDose.user_id)), func.count()).where(
        MedicationDose.recorded_at >= r.lo, MedicationDose.recorded_at < r.hi)).one()
    meds_created = db.scalar(select(func.count()).select_from(Medication).where(
        Medication.created_at >= r.lo, Medication.created_at < r.hi)) or 0
    fit = db.execute(select(func.count(distinct(Workout.user_id)), func.count()).where(
        Workout.status == "completed", Workout.started_at >= r.lo, Workout.started_at < r.hi)).one()
    return [
        {"feature": "water", "label": "Water tracking", "users": water[0], "records": water[1], "record_label": "drinks logged"},
        {"feature": "medication", "label": "Medication", "users": meds[0], "records": meds[1], "record_label": "doses recorded",
         "extra": {"schedules_created": meds_created}},
        {"feature": "fitness", "label": "Fitness", "users": fit[0], "records": fit[1], "record_label": "workouts completed"},
    ]


# ---------- recent activity ----------

def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:1] + "•••@" + domain) if domain else "•••"


AUDIT_HIDDEN = {"admin.login_password_ok"}
_ACTION_WORDS = re.compile(r"[._]")


def recent_activity(db: Session, *, can_payments: bool, can_audit: bool, limit: int = 20) -> list[dict]:
    items: list[dict] = []

    for u in db.execute(select(User).order_by(User.created_at.desc()).limit(limit)).scalars():
        items.append({"type": "registration", "at": as_utc(u.created_at), "title": "New registration",
                      "detail": f"{u.first_name} · {mask_email(u.email)}"})

    for t in db.execute(select(PaymentTransaction).where(PaymentTransaction.environment == "production")
                        .order_by(PaymentTransaction.purchased_at.desc()).limit(limit)).scalars():
        kind = {"initial_purchase": ("subscription", "New subscription")}.get(t.kind, ("payment", "Payment received"))
        if t.status == "refunded":
            kind = ("refund", "Payment refunded")
        elif t.status in ("failed", "pending"):
            kind = ("payment_failed" if t.status == "failed" else "payment_pending",
                    "Payment failed" if t.status == "failed" else "Payment pending")
        if kind[0] != "subscription" and not can_payments:
            continue
        detail = t.product_id
        if can_payments and t.amount is not None and t.currency:
            detail = f"{t.currency} {_money(t.amount)} · {t.product_id}"
        items.append({"type": kind[0], "at": as_utc(t.purchased_at), "title": kind[1], "detail": detail})

    for e in db.execute(select(WebhookEvent).where(
            WebhookEvent.provider == "revenuecat", WebhookEvent.event_type.in_(("CANCELLATION", "BILLING_ISSUE")))
            .order_by(WebhookEvent.received_at.desc()).limit(limit)).scalars():
        summary = e.summary or {}
        if str(summary.get("environment") or "").upper() == "SANDBOX":
            continue
        if e.event_type == "BILLING_ISSUE" and not can_payments:
            continue
        title = "Subscription cancelled" if e.event_type == "CANCELLATION" else "Payment failed"
        items.append({"type": "cancellation" if e.event_type == "CANCELLATION" else "payment_failed",
                      "at": as_utc(e.received_at), "title": title, "detail": summary.get("product_id") or None})

    if can_audit:
        for a in db.execute(select(AuditLog).where(AuditLog.action.not_in(AUDIT_HIDDEN))
                            .order_by(AuditLog.created_at.desc()).limit(limit)).scalars():
            items.append({"type": "admin_action", "at": as_utc(a.created_at),
                          "title": _ACTION_WORDS.sub(" ", a.action).capitalize(),
                          "detail": a.actor_email})

    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


def overview(db: Session, r: Range, *, can_payments: bool, can_audit: bool) -> dict:
    users = user_stats(db, r)
    return {
        "range": {"from": r.start, "to": r.end},
        "generated_at": utcnow(),
        "users": users,
        "subscriptions": subscription_stats(db, r, users),
        "revenue": revenue_stats(db, r) if can_payments else None,
        "series": {
            "user_growth": user_growth(db, r),
            "active_users": active_users_daily(db, r),
            "conversion_monthly": conversion_monthly(db),
            "revenue_monthly": revenue_monthly(db) if can_payments else None,
        },
        "feature_usage": feature_usage(db, r),
        "recent_activity": recent_activity(db, can_payments=can_payments, can_audit=can_audit),
    }
