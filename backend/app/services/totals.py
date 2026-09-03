"""Report totals — always computed, never stored (docs/decisions.md, Decision 3).

A stored copy can drift from the lines it summarises; a computed one cannot. The list
view uses `totals_subquery()` so a page of N reports costs one aggregate join rather than
N separate SUM queries.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Subquery

from app.models import ExpenseLine


def totals_subquery() -> Subquery:
    """report_id -> SUM(amount), for joining against a set of reports in one query."""
    return (
        select(
            ExpenseLine.report_id.label("report_id"),
            func.coalesce(func.sum(ExpenseLine.amount), 0).label("total"),
        )
        .group_by(ExpenseLine.report_id)
        .subquery()
    )


def report_total(db: Session, report_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(ExpenseLine.amount), 0)).where(
            ExpenseLine.report_id == report_id
        )
    )
    return Decimal(total or 0)


def totals_for(db: Session, report_ids: list[int]) -> dict[int, Decimal]:
    """Totals for many reports in one query — used wherever a list of reports is returned."""
    if not report_ids:
        return {}

    rows = db.execute(
        select(ExpenseLine.report_id, func.coalesce(func.sum(ExpenseLine.amount), 0))
        .where(ExpenseLine.report_id.in_(report_ids))
        .group_by(ExpenseLine.report_id)
    ).all()

    totals = {report_id: Decimal(total) for report_id, total in rows}
    # Reports with no lines have no row in the aggregate; their total is zero, not missing.
    return {report_id: totals.get(report_id, Decimal("0")) for report_id in report_ids}
