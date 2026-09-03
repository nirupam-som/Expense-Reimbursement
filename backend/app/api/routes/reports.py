import csv
import io
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_approver
from app.db.session import get_db
from app.models import ExpenseReport, User
from app.models.enums import ReportStatus
from app.schemas.bulk import BulkDecisionRequest, BulkResultOut
from app.schemas.report import (
    ReportCreate,
    ReportDetailOut,
    ReportOut,
    ReportPageOut,
    ReportUpdate,
    RejectRequest,
)
from app.services.bulk import bulk_decide
from app.services.lifecycle import Action, Refusal, apply_transition
from app.services.reports_query import ReportQuery, search_reports
from app.services.totals import report_total, totals_subquery

router = APIRouter(prefix="/reports", tags=["reports"])

# How each refusal reaches the client. Authorization refusals are 403; state problems are
# 409 (the request was well-formed, the report just isn't in a state that allows it);
# missing input is 400.
_REFUSAL_STATUS = {
    Refusal.not_owner: status.HTTP_403_FORBIDDEN,
    Refusal.owner_is_approver: status.HTTP_403_FORBIDDEN,
    Refusal.not_approver_role: status.HTTP_403_FORBIDDEN,
    Refusal.wrong_status: status.HTTP_409_CONFLICT,
    Refusal.no_lines: status.HTTP_400_BAD_REQUEST,
    Refusal.missing_reason: status.HTTP_400_BAD_REQUEST,
}


def _serialise(report: ExpenseReport, total, *, detail: bool = False):
    # `total` is not a column — it is attached here, freshly computed, on the way out.
    report.total = total
    schema = ReportDetailOut if detail else ReportOut
    return schema.model_validate(report)


def _load(db: Session, report_id: int) -> ExpenseReport:
    report = db.get(
        ExpenseReport,
        report_id,
        options=[
            selectinload(ExpenseReport.owner),
            selectinload(ExpenseReport.lines),
            selectinload(ExpenseReport.approvers),
        ],
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return report


def _require_visible(report: ExpenseReport, actor: User) -> None:
    """Owners see their own reports; approvers see everyone's."""
    if actor.is_approver or report.owner_id == actor.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You can only view your own expense reports.",
    )


def _require_owner(report: ExpenseReport, actor: User) -> None:
    if report.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the report's owner can change it.",
        )


def _transition(
    db: Session, report: ExpenseReport, action: Action, actor: User, reason: str | None = None
) -> ReportDetailOut:
    outcome = apply_transition(db, report=report, action=action, actor=actor, reason=reason)

    if not outcome.allowed:
        # Every refusal carries an explanation — the brief requires an illegal transition
        # to be rejected *with a message saying why*, not just a bare status code.
        raise HTTPException(
            status_code=_REFUSAL_STATUS.get(outcome.code, status.HTTP_400_BAD_REQUEST),
            detail=outcome.message,
        )

    db.commit()
    db.refresh(report)
    return _serialise(report, report_total(db, report.id), detail=True)


# --------------------------------------------------------------------------------------
# Collection routes. These are declared before /{report_id} so a literal path segment is
# never swallowed by the path parameter.
# --------------------------------------------------------------------------------------


@router.get("", response_model=ReportPageOut)
def list_reports(
    search: str | None = None,
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    owner_id: int | None = None,
    approver_id: int | None = None,
    assigned_to_me: bool = False,
    include_archived: bool = False,
    archived_only: bool = False,
    sort: str = "created_at",
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportPageOut:
    """One list across every employee the viewer can see.

    Search, filtering, sorting and pagination all happen in the database — the browser
    never receives rows it then has to filter.
    """
    result = search_reports(
        db,
        current_user,
        ReportQuery(
            search=search,
            status=report_status,
            owner_id=owner_id,
            approver_id=approver_id,
            assigned_to_me=assigned_to_me,
            include_archived=include_archived,
            archived_only=archived_only,
            sort=sort,
            direction=direction,
            page=page,
            page_size=page_size,
        ),
    )

    return ReportPageOut(
        items=[_serialise(report, total) for report, total in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("", response_model=ReportDetailOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    """Every user creates reports for themselves — the owner is always the caller."""
    report = ExpenseReport(
        owner_id=current_user.id,
        title=payload.title,
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        status=ReportStatus.draft,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return _serialise(_load(db, report.id), report_total(db, report.id), detail=True)


@router.post("/bulk-approve", response_model=BulkResultOut)
def bulk_approve(
    payload: BulkDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> BulkResultOut:
    return BulkResultOut(
        **bulk_decide(
            db, actor=current_user, report_ids=payload.report_ids, action=Action.approve
        )
    )


@router.post("/bulk-reject", response_model=BulkResultOut)
def bulk_reject(
    payload: BulkDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> BulkResultOut:
    # One reason covers the batch. Each report still gets its own history row carrying it.
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejecting reports requires a reason.",
        )

    return BulkResultOut(
        **bulk_decide(
            db,
            actor=current_user,
            report_ids=payload.report_ids,
            action=Action.reject,
            reason=payload.reason,
        )
    )


@router.get("/export/unpaid.csv")
def export_unpaid(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> StreamingResponse:
    """The reimbursements due: every approved report awaiting payment, as CSV.

    Built server-side from a live query — the same Approved-and-not-Paid filter the
    dashboard's "total due" uses — rather than from whatever the browser happens to be
    holding.
    """
    totals = totals_subquery()

    rows = db.execute(
        select(ExpenseReport, totals.c.total)
        .outerjoin(totals, totals.c.report_id == ExpenseReport.id)
        .options(selectinload(ExpenseReport.owner))
        .where(ExpenseReport.status == ReportStatus.approved)
        .where(ExpenseReport.is_archived.is_(False))
        .order_by(ExpenseReport.decided_at.asc())
    ).all()

    def generate() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush() -> str:
            value = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            return value

        writer.writerow(
            [
                "Report ID",
                "Title",
                "Owner",
                "Owner Email",
                "Period Start",
                "Period End",
                "Submitted At",
                "Approved At",
                "Amount Due",
            ]
        )
        yield flush()

        for report, total in rows:
            writer.writerow(
                [
                    report.id,
                    report.title,
                    report.owner.full_name,
                    report.owner.email,
                    report.date_range_start.isoformat(),
                    report.date_range_end.isoformat(),
                    report.submitted_at.isoformat() if report.submitted_at else "",
                    report.decided_at.isoformat() if report.decided_at else "",
                    f"{(total or 0):.2f}",
                ]
            )
            yield flush()

    filename = f"reimbursements-due-{datetime.now().date().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------------------
# Single-report routes
# --------------------------------------------------------------------------------------


@router.get("/{report_id}", response_model=ReportDetailOut)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    report = _load(db, report_id)
    _require_visible(report, current_user)
    return _serialise(report, report_total(db, report.id), detail=True)


@router.patch("/{report_id}", response_model=ReportDetailOut)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    report = _load(db, report_id)
    _require_owner(report, current_user)

    if report.status is not ReportStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A report can only be edited while it is a Draft; this one is "
            f"{report.status.value}.",
        )

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(report, field, value)

    if report.date_range_end < report.date_range_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The end of the date range cannot be before its start.",
        )

    db.commit()
    db.refresh(report)
    return _serialise(report, report_total(db, report.id), detail=True)


@router.post("/{report_id}/archive", response_model=ReportDetailOut)
def archive_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    """Hides a report from default views. Status, lines and history are untouched."""
    report = _load(db, report_id)
    _require_owner(report, current_user)
    report.is_archived = True
    db.commit()
    db.refresh(report)
    return _serialise(report, report_total(db, report.id), detail=True)


@router.post("/{report_id}/restore", response_model=ReportDetailOut)
def restore_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    report = _load(db, report_id)
    _require_owner(report, current_user)
    report.is_archived = False
    db.commit()
    db.refresh(report)
    return _serialise(report, report_total(db, report.id), detail=True)


@router.post("/{report_id}/submit", response_model=ReportDetailOut)
def submit_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportDetailOut:
    return _transition(db, _load(db, report_id), Action.submit, current_user)


@router.post("/{report_id}/approve", response_model=ReportDetailOut)
def approve_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> ReportDetailOut:
    return _transition(db, _load(db, report_id), Action.approve, current_user)


@router.post("/{report_id}/reject", response_model=ReportDetailOut)
def reject_report(
    report_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> ReportDetailOut:
    return _transition(db, _load(db, report_id), Action.reject, current_user, payload.reason)


@router.post("/{report_id}/mark-paid", response_model=ReportDetailOut)
def mark_report_paid(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> ReportDetailOut:
    return _transition(db, _load(db, report_id), Action.mark_paid, current_user)
