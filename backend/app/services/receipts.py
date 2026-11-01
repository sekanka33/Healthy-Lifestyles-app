"""PDF receipts, regenerated on demand from the immutable payment row (nothing is stored).

The app store (Apple / Google) is the merchant of record and issues the official invoice; this is
the app's own record of the payment, and says so on the page.
"""

from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.db.base import as_utc
from app.models.billing import PaymentTransaction
from app.models.user import User

NAVY = colors.HexColor("#0B1E37")
MUTED = colors.HexColor("#6B7489")
CYAN = colors.HexColor("#04C3D5")
DANGER = colors.HexColor("#D64545")

STORE_NAMES = {
    "app_store": "Apple App Store",
    "play_store": "Google Play",
    "stripe": "Stripe",
    "promotional": "Promotional grant",
}
KIND_NAMES = {
    "initial_purchase": "New subscription",
    "renewal": "Renewal",
    "restore": "Restored purchase",
    "product_change": "Plan change",
}


def format_amount(amount: Decimal | None, currency: str | None) -> str:
    if amount is None:
        return "Not provided by the store"
    q = amount.quantize(Decimal("0.01"))
    return f"{q:,.2f} {currency or ''}".strip()


def render_receipt(txn: PaymentTransaction, user: User) -> bytes:
    settings = get_settings()
    tz = ZoneInfo(user.timezone or "UTC")

    def local(dt):
        return as_utc(dt).astimezone(tz).strftime("%d %b %Y, %H:%M %Z") if dt else "—"

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    c.setTitle(f"Receipt {txn.receipt_number}")
    c.setAuthor(settings.app_name)
    w, h = A4
    x = 20 * mm
    y = h - 25 * mm

    c.setFillColor(CYAN)
    c.circle(x + 4 * mm, y + 1.5 * mm, 4 * mm, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x + 11 * mm, y, settings.app_name)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(w - x, y, "Receipt")

    y -= 18 * mm
    rows = [
        ("Receipt number", txn.receipt_number or "—"),
        ("Date", local(txn.purchased_at)),
        ("Billed to", f"{user.first_name} {user.last_name or ''}".strip() + f" <{user.email}>"),
        ("Description", f"{settings.app_name} Premium — {KIND_NAMES.get(txn.kind, txn.kind)}"),
        ("Product", txn.product_id),
        ("Service period", f"{local(txn.period_start)}  to  {local(txn.period_end)}"),
        ("Paid via", STORE_NAMES.get(txn.provider, txn.provider)),
        ("Store transaction", txn.provider_transaction_id),
        ("Status", txn.status.capitalize()),
    ]
    if txn.environment == "sandbox":
        rows.append(("Environment", "Sandbox (test purchase — no money was charged)"))
    for label, value in rows:
        c.setFont("Helvetica", 10)
        c.setFillColor(MUTED)
        c.drawString(x, y, label)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 45 * mm, y, str(value)[:90])
        y -= 8 * mm

    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#E6E9EE"))
    c.line(x, y, w - x, y)
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Total")
    c.drawRightString(w - x, y, format_amount(txn.amount, txn.currency))
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawRightString(w - x, y, "Tax: " + (format_amount(txn.tax_amount, txn.currency) if txn.tax_amount is not None
                                          else "included where applicable, as charged by the store"))

    if txn.status in ("refunded", "chargeback"):
        c.saveState()
        c.setFillColor(DANGER)
        c.setFont("Helvetica-Bold", 60)
        c.translate(w / 2, h / 2)
        c.rotate(30)
        c.setFillAlpha(0.18)
        c.drawCentredString(0, 0, txn.status.upper())
        c.restoreState()

    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    store = STORE_NAMES.get(txn.provider, "the store")
    c.drawString(x, 30 * mm, f"Payment was processed by {store}, which issues the official invoice for this purchase.")
    c.drawString(x, 25 * mm, f"Questions? Contact {settings.support_email}. Manage or cancel your subscription in your store account settings.")
    c.showPage()
    c.save()
    return buf.getvalue()
