"""Finding reports: search, filter, sort, pagination — all in SQL, never in the browser.

The caller's visibility scope is applied first, as the base WHERE clause. User-supplied
filters are layered on top with AND, so a filter parameter can only ever narrow what a
user can see, never widen it: an employee passing `owner_id=<someone else>` gets an empty
page, not another employee's reports.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ExpenseReport, ReportApprover, User
from app.models.enums import ReportStatus
from app.services.totals import totals_subquery

MAX_PAGE_SIZE = 100

# Allow-list, not free text: the sort parameter can never become an arbitrary SQL
# expression, and an unknown value falls back to a default instead of erroring.
SORTABLE = frozenset({"submitted_at", "status", "total", "created_at", "title"})
DEFAULT_SORT = "created_at"


@dataclass
class ReportQuery:
    search: str | None = None
    status: ReportStatus | None = None
    owner_id: int | None = None
    approver_id: int | None = None
    assigned_to_me: bool = False
    include_archived: bool = False
    archived_only: bool = False
    sort: str = DEFAULT_SORT
    direction: str = "desc"
    page: int = 1
    page_size: int = 20


@dataclass
class ReportPage:
    items: list[tuple[ExpenseReport, Decimal]]
    total: int
    page: int
    page_size: int


def visible_scope(actor: User) -> Select:
    """Base query: what this user is allowed to see at all.

    Approvers can see every report (that is the point of the system — finance and
    approvers need the whole picture). Everyone else sees only their own.
    """
    stmt = select(ExpenseReport)
    if not actor.is_approver:
        stmt = stmt.where(ExpenseReport.owner_id == actor.id)
    return stmt


def search_reports(db: Session, actor: User, query: ReportQuery) -> ReportPage:
    totals = totals_subquery()

    stmt = visible_scope(actor).outerjoin(totals, totals.c.report_id == ExpenseReport.id)

    if query.archived_only:
        stmt = stmt.where(ExpenseReport.is_archived.is_(True))
    elif not query.include_archived:
        # Archiving removes a report from the default view without destroying anything.
        stmt = stmt.where(ExpenseReport.is_archived.is_(False))

    if query.search:
        # ILIKE with a leading wildcard cannot use a B-tree index. Acceptable at this
        # scale; docs/schema.md records the pg_trgm upgrade path.
        stmt = stmt.where(ExpenseReport.title.ilike(f"%{query.search.strip()}%"))

    if query.status is not None:
        stmt = stmt.where(ExpenseReport.status == query.status)

    if query.owner_id is not None:
        stmt = stmt.where(ExpenseReport.owner_id == query.owner_id)

    assigned_to = query.approver_id
    if query.assigned_to_me:
        assigned_to = actor.id
    if assigned_to is not None:
        # IN over the join table rather than a JOIN, so a report assigned to several
        # approvers cannot appear twice in the page.
        stmt = stmt.where(
            ExpenseReport.id.in_(
                select(ReportApprover.report_id).where(ReportApprover.approver_id == assigned_to)
            )
        )

    total_matches = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_key = query.sort if query.sort in SORTABLE else DEFAULT_SORT
    sort_column = {
        "submitted_at": ExpenseReport.submitted_at,
        "status": ExpenseReport.status,
        "total": func.coalesce(totals.c.total, 0),
        "created_at": ExpenseReport.created_at,
        "title": ExpenseReport.title,
    }[sort_key]
    ordering = sort_column.desc() if query.direction == "desc" else sort_column.asc()

    page = max(1, query.page)
    page_size = min(max(1, query.page_size), MAX_PAGE_SIZE)

    rows = db.execute(
        stmt.add_columns(func.coalesce(totals.c.total, 0))
        .options(selectinload(ExpenseReport.owner))
        # Ties on the sort key would otherwise let a row appear on two pages, or on
        # none: id is the tiebreaker that makes paging stable.
        .order_by(ordering, ExpenseReport.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()

    return ReportPage(
        items=[(report, Decimal(total)) for report, total in rows],
        total=total_matches,
        page=page,
        page_size=page_size,
    )
