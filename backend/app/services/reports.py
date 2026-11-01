"""Water, fitness and medication reports: data, PDF and email text.

Periods are local calendar ranges in the user's zone: daily = yesterday, weekly = last Monday–Sunday,
monthly = last calendar month. Medication emails respect `medication_report_detail`:
"summary_only" (default) never puts medication names in the email or attaches the PDF.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services import fitness as fitness_svc
from app.services import hydration as hydration_svc
from app.services import medication as medication_svc

NAVY, CYAN, MUTED = colors.HexColor("#0B1E37"), colors.HexColor("#04C3D5"), colors.HexColor("#6B7489")
KINDS = ("water", "fitness", "medication")
PREMIUM_KINDS = ("fitness", "medication")


def previous_period(today: date, frequency: str) -> tuple[date, date]:
    if frequency == "daily":
        d = today - timedelta(days=1)
        return d, d
    if frequency == "weekly":
        this_monday = today - timedelta(days=today.isoweekday() - 1)
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def label(first: date, last: date) -> str:
    if first == last:
        return first.strftime("%A %d %B %Y")
    return f"{first:%d %b} – {last:%d %b %Y}"


@dataclass
class Report:
    kind: str
    title: str
    first: date
    last: date
    headline: str  # one safe sentence, fine for an email preview
    lines: list[str]  # email body lines (may contain details, see `detailed`)
    table: list[list[str]]  # PDF table incl. header row
    empty: bool


def water(db: Session, user: User, first: date, last: date) -> Report:
    days = hydration_svc.history(db, user, first, last)
    met = sum(d.goal_met for d in days)
    avg = round(sum(d.total_ml for d in days) / len(days)) if days else 0
    streak = best = 0
    for d in days:
        streak = streak + 1 if d.goal_met else 0
        best = max(best, streak)
    rows = [["Day", "Water", "Goal", "Met"]] + [
        [f"{d.date:%a %d %b}", f"{d.total_ml:,} ml", f"{d.goal_ml:,} ml", "Yes" if d.goal_met else ""] for d in days]
    return Report("water", "Water report", first, last,
                  headline=f"You met your water goal on {met} of {len(days)} day{'s' if len(days) != 1 else ''}.",
                  lines=[f"Daily average: {avg:,} ml", f"Best streak: {best} day{'s' if best != 1 else ''}"],
                  table=rows, empty=sum(d.total_ml for d in days) == 0)


def fitness(db: Session, user: User, first: date, last: date) -> Report:
    ws = sorted(fitness_svc.list_workouts(db, user, first, last), key=lambda w: w.started_at)
    km = sum(w.distance_m for w in ws) / 1000
    minutes = sum(w.active_duration_s for w in ws) / 60
    names = {"walking": "Walk", "jogging": "Jog", "running": "Run"}
    rows = [["Date", "Activity", "Distance", "Time"]] + [
        [f"{w.started_at:%a %d %b}", names.get(w.activity_type, w.activity_type), f"{w.distance_m / 1000:.2f} km",
         f"{w.active_duration_s // 60} min"] for w in ws]
    return Report("fitness", "Fitness report", first, last,
                  headline=f"{len(ws)} workout{'s' if len(ws) != 1 else ''}, {km:.1f} km in total.",
                  lines=[f"Active time: {round(minutes)} minutes"], table=rows, empty=not ws)


def medication(db: Session, user: User, first: date, last: date) -> Report:
    rows_ = medication_svc.adherence(db, user, first, last)
    due = sum(r.scheduled for r in rows_)
    taken = sum(r.taken for r in rows_)
    pct = f"{round(100 * taken / due)}%" if due else "—"
    table = [["Medication", "Taken", "Skipped", "Missed", "Not logged"]] + [
        [r.medication_name, f"{r.taken}/{r.scheduled}" if r.scheduled else f"{r.as_needed_taken} as needed",
         str(r.skipped), str(r.missed), str(r.unrecorded)] for r in rows_]
    return Report("medication", "Medication report", first, last,
                  headline=f"Doses logged as taken: {pct} ({taken} of {due}).",
                  lines=[f"{r.medication_name}: {r.taken} of {r.scheduled} taken, {r.unrecorded} not logged"
                         for r in rows_ if r.scheduled],
                  table=table, empty=not rows_)


BUILDERS = {"water": water, "fitness": fitness, "medication": medication}


def build(db: Session, user: User, kind: str, first: date, last: date) -> Report:
    return BUILDERS[kind](db, user, first, last)


def render_pdf(report: Report, user: User) -> bytes:
    buf = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"{report.title} {label(report.first, report.last)}",
                            author=get_settings().app_name)
    h = styles["Title"].clone("h", textColor=NAVY, alignment=0)
    body = styles["BodyText"].clone("b", textColor=NAVY)
    small = styles["BodyText"].clone("s", textColor=MUTED, fontSize=8.5)
    story = [Paragraph(f"{get_settings().app_name} — {report.title}", h),
             Paragraph(f"{user.first_name} · {label(report.first, report.last)}", body), Spacer(1, 6 * mm),
             Paragraph(report.headline, body)]
    story += [Paragraph(line, body) for line in report.lines if report.kind != "medication"]
    story.append(Spacer(1, 6 * mm))
    if len(report.table) > 1:
        t = Table(report.table, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CYAN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4FEFE")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E6E9EE")),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Nothing was logged in this period.", body))
    story.append(Spacer(1, 8 * mm))
    if report.kind == "medication":
        story.append(Paragraph("This report shows what you logged in the app. It is not medical advice; "
                               "talk to your healthcare professional about your medication.", small))
    if report.kind == "fitness":
        story.append(Paragraph("Distances come from GPS and may differ slightly from other devices.", small))
    doc.build(story)
    return buf.getvalue()


def email_text(report: Report, user: User, *, detailed: bool, unsubscribe_url: str | None) -> str:
    lines = [f"Hi {user.first_name},", "", f"Your {report.title.lower()} for {label(report.first, report.last)}:", "",
             report.headline]
    if report.kind != "medication" or detailed:
        lines += report.lines
    else:
        lines += ["", "Open the app to see the details for each medication."]
    if detailed or report.kind != "medication":
        lines += ["", "The full report is attached as a PDF."]
    lines += ["", "— " + get_settings().app_name]
    if unsubscribe_url:
        lines += ["", f"Don't want these emails? Unsubscribe: {unsubscribe_url}",
                  "You can also change report emails in the app under Profile → Email & reports."]
    return "\n".join(lines)
