"""Stale-approval alerts (goal 10).

Computed live on every read, never by a background job and never from a stored flag:

  stale  = status is Submitted AND submitted_at is older than STALE_AFTER_DAYS
  hidden = this approver dismissed it less than STALE_REALERT_AFTER_DAYS ago

Because the dismissal is a *timestamp* rather than a boolean, an alert comes back on its
own once the re-alert window passes — there is no scheduled task that has to remember to
un-hide it, and nothing to fall behind if a run is missed.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import ExpenseReport, ReportApprover, StaleAlertDismissal, User
from app.models.enums import ReportStatus


def stale_reports(db: Session, actor: User) -> list[tuple[ExpenseReport, int, bool]]:
    """Returns (report, days_waiting, can_dismiss) for every alert this user should see.

    Approvers see the whole stale queue; employees see only their own stale reports, as
    information — they cannot dismiss anything.
    """
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(days=settings.stale_after_days)
    dismissal_still_valid = now - timedelta(days=settings.stale_realert_after_days)

    dismissal = (
        select(StaleAlertDismissal)
        .where(StaleAlertDismissal.approver_id == actor.id)
        .subquery()
    )

    stmt = (
        select(ExpenseReport)
        .outerjoin(dismissal, dismissal.c.report_id == ExpenseReport.id)
        .where(ExpenseReport.status == ReportStatus.submitted)
        .where(ExpenseReport.submitted_at < stale_before)
        .where(ExpenseReport.is_archived.is_(False))
        .where(
            # Never dismissed by me, or dismissed long enough ago that it is due back.
            (dismissal.c.dismissed_at.is_(None))
            | (dismissal.c.dismissed_at < dismissal_still_valid)
        )
        .options(selectinload(ExpenseReport.owner))
        .order_by(ExpenseReport.submitted_at.asc())
    )

    if not actor.is_approver:
        stmt = stmt.where(ExpenseReport.owner_id == actor.id)

    reports = list(db.scalars(stmt).all())

    assigned_ids = set()
    if reports and actor.is_approver:
        assigned_ids = set(
            db.scalars(
                select(ReportApprover.report_id).where(
                    and_(
                        ReportApprover.approver_id == actor.id,
                        ReportApprover.report_id.in_([r.id for r in reports]),
                    )
                )
            ).all()
        )

    return [
        (
            report,
            (now - report.submitted_at).days if report.submitted_at else 0,
            report.id in assigned_ids,
        )
        for report in reports
    ]


def can_dismiss(db: Session, report_id: int, actor: User) -> bool:
    """Dismissal is limited to approvers the report is actually assigned to."""
    if not actor.is_approver:
        return False
    return (
        db.scalar(
            select(ReportApprover.report_id).where(
                and_(
                    ReportApprover.report_id == report_id,
                    ReportApprover.approver_id == actor.id,
                )
            )
        )
        is not None
    )


def dismiss(db: Session, report_id: int, actor: User) -> None:
    """Upsert: re-dismissing a reappeared alert refreshes the clock, it does not stack."""
    existing = db.get(StaleAlertDismissal, {"report_id": report_id, "approver_id": actor.id})
    if existing is None:
        db.add(StaleAlertDismissal(report_id=report_id, approver_id=actor.id))
    else:
        existing.dismissed_at = datetime.now(timezone.utc)
