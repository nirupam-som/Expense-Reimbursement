"""Dashboard aggregates — computed in SQL, scoped by the same rules as every other read.

An employee's dashboard reflects their own reports; an approver's reflects everything
they can see. Archived reports are excluded throughout, consistently with every other
default view.

"This week" means the current ISO week (Monday 00:00, in the database's timezone), and
week counts come from the immutable event log rather than from a report's current status
— a report approved on Monday and paid on Wednesday must count in *both* figures, which
a status-based count could not express.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import ExpenseLine, ExpenseReport, ReportEvent, User
from app.models.enums import ExpenseCategory, ReportStatus

WEEKS_ON_CHART = 8


def _visible_reports(actor: User) -> Select:
    stmt = select(ExpenseReport.id).where(ExpenseReport.is_archived.is_(False))
    if not actor.is_approver:
        stmt = stmt.where(ExpenseReport.owner_id == actor.id)
    return stmt


def _monday_of(moment: datetime) -> datetime:
    start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day - timedelta(days=start_of_day.weekday())


def build_dashboard(db: Session, actor: User) -> dict:
    visible = _visible_reports(actor).subquery()
    now = datetime.now(timezone.utc)
    week_start = _monday_of(now)

    awaiting_approval = (
        db.scalar(
            select(func.count(ExpenseReport.id))
            .where(ExpenseReport.id.in_(select(visible.c.id)))
            .where(ExpenseReport.status == ReportStatus.submitted)
        )
        or 0
    )

    # Reimbursements due: approved but not yet paid. The CSV export runs this same
    # filter, so the headline number and the exported file cannot drift apart.
    total_due = (
        db.scalar(
            select(func.coalesce(func.sum(ExpenseLine.amount), 0))
            .join(ExpenseReport, ExpenseReport.id == ExpenseLine.report_id)
            .where(ExpenseReport.id.in_(select(visible.c.id)))
            .where(ExpenseReport.status == ReportStatus.approved)
        )
        or 0
    )

    def _events_this_week(to_status: ReportStatus) -> int:
        return (
            db.scalar(
                select(func.count(ReportEvent.id))
                .where(ReportEvent.report_id.in_(select(visible.c.id)))
                .where(ReportEvent.to_status == to_status)
                .where(ReportEvent.created_at >= week_start)
            )
            or 0
        )

    by_status_rows = db.execute(
        select(ExpenseReport.status, func.count(ExpenseReport.id))
        .where(ExpenseReport.id.in_(select(visible.c.id)))
        .group_by(ExpenseReport.status)
    ).all()
    counted = {status: count for status, count in by_status_rows}
    by_status = [
        {"status": status, "count": counted.get(status, 0)} for status in ReportStatus
    ]

    by_category_rows = db.execute(
        select(
            ExpenseLine.category,
            func.coalesce(func.sum(ExpenseLine.amount), 0),
            func.count(ExpenseLine.id),
        )
        .join(ExpenseReport, ExpenseReport.id == ExpenseLine.report_id)
        .where(ExpenseReport.id.in_(select(visible.c.id)))
        .group_by(ExpenseLine.category)
    ).all()
    # Grouped by *line* category, not by report: one report can span several categories,
    # so attributing a whole report to a single category would be wrong.
    categorised = {category: (total, count) for category, total, count in by_category_rows}
    by_category = [
        {
            "category": category,
            "total": Decimal(categorised.get(category, (0, 0))[0]),
            "line_count": categorised.get(category, (0, 0))[1],
        }
        for category in ExpenseCategory
    ]

    return {
        "awaiting_approval": awaiting_approval,
        "total_due": Decimal(total_due),
        "approved_this_week": _events_this_week(ReportStatus.approved),
        "paid_this_week": _events_this_week(ReportStatus.paid),
        "by_status": by_status,
        "by_category": by_category,
        "weekly_paid": _weekly_paid(db, visible, week_start),
    }


def _weekly_paid(db: Session, visible, week_start: datetime) -> list[dict]:
    """Total reimbursements paid per week for the last 8 weeks.

    Weeks with nothing paid are returned as zero rather than omitted — a chart that
    silently skips empty weeks misrepresents the trend.
    """
    earliest = week_start - timedelta(weeks=WEEKS_ON_CHART - 1)

    bucket = func.date_trunc("week", ExpenseReport.paid_at)
    rows = db.execute(
        select(bucket, func.coalesce(func.sum(ExpenseLine.amount), 0))
        .join(ExpenseLine, ExpenseLine.report_id == ExpenseReport.id)
        .where(ExpenseReport.id.in_(select(visible.c.id)))
        .where(ExpenseReport.paid_at.isnot(None))
        .where(ExpenseReport.paid_at >= earliest)
        .group_by(bucket)
    ).all()

    paid_by_week: dict[date, Decimal] = {
        week.date(): Decimal(total) for week, total in rows if week is not None
    }

    return [
        {
            "week_start": (earliest + timedelta(weeks=offset)).date(),
            "total": paid_by_week.get((earliest + timedelta(weeks=offset)).date(), Decimal("0")),
        }
        for offset in range(WEEKS_ON_CHART)
    ]
