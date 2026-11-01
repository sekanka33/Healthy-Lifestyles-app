import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EntitlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    product_id: str | None
    store: str | None
    expires_at: datetime | None
    will_renew: bool
    environment: str
    last_verified_at: datetime | None


class BillingStatusOut(BaseModel):
    plan: Literal["free", "premium"]
    entitlement: EntitlementOut | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    product_id: str
    kind: str
    status: str
    amount: Decimal | None
    currency: str | None
    purchased_at: datetime
    period_end: datetime | None
    environment: str
    receipt_number: str | None
    has_receipt: bool
