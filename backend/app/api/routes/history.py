"""The immutable timeline (goal 9).

Note what this module does not contain: there is no PATCH and no DELETE for either
report_events or report_comments. The capability to rewrite history does not exist in the
API at all — and the application's database role additionally has no UPDATE/DELETE grant
on those two tables, so even a future mistake in application code cannot rewrite them.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ExpenseReport, ReportComment, ReportEvent, User
from app.schemas.history import CommentCreate, TimelineEntryOut
from app.schemas.user import UserSummary

router = APIRouter(prefix="/reports", tags=["timeline"])


def _visible_report(db: Session, report_id: int, actor: User) -> ExpenseReport:
    report = db.get(ExpenseReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    if not actor.is_approver and report.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own expense reports.",
        )
    return report


@router.get("/{report_id}/timeline", response_model=list[TimelineEntryOut])
def get_timeline(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TimelineEntryOut]:
    """Every status change and every comment, oldest first, as one stream."""
    _visible_report(db, report_id, current_user)

    events = db.scalars(
        select(ReportEvent)
        .where(ReportEvent.report_id == report_id)
        .options(selectinload(ReportEvent.actor))
        .order_by(ReportEvent.created_at, ReportEvent.id)
    ).all()

    comments = db.scalars(
        select(ReportComment)
        .where(ReportComment.report_id == report_id)
        .options(selectinload(ReportComment.author))
        .order_by(ReportComment.created_at, ReportComment.id)
    ).all()

    entries = [
        TimelineEntryOut(
            kind="status_change",
            id=event.id,
            at=event.created_at,
            actor=UserSummary.model_validate(event.actor),
            from_status=event.from_status,
            to_status=event.to_status,
            reason=event.reason,
        )
        for event in events
    ] + [
        TimelineEntryOut(
            kind="comment",
            id=comment.id,
            at=comment.created_at,
            actor=UserSummary.model_validate(comment.author),
            body=comment.body,
        )
        for comment in comments
    ]

    return sorted(entries, key=lambda entry: (entry.at, entry.kind, entry.id))


@router.post(
    "/{report_id}/comments", response_model=TimelineEntryOut, status_code=status.HTTP_201_CREATED
)
def add_comment(
    report_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineEntryOut:
    """The owner or any approver may comment. Once written, a comment cannot be changed."""
    _visible_report(db, report_id, current_user)

    comment = ReportComment(
        report_id=report_id, author_id=current_user.id, body=payload.body.strip()
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return TimelineEntryOut(
        kind="comment",
        id=comment.id,
        at=comment.created_at,
        actor=UserSummary.model_validate(current_user),
        body=comment.body,
    )
