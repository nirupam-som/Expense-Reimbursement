"""Assigned approvers (goal 5).

Any number of approvers can be assigned to a report, and an approver can be assigned to
any number of reports. Assignment decides whose queue a report shows up in — it is not an
authorization gate, so an unassigned approver can still decide on a report they don't own
(docs/decisions.md, Decision 6).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ExpenseReport, ReportApprover, User
from app.models.enums import UserRole
from app.schemas.report import AssignApproverRequest
from app.schemas.user import UserSummary

router = APIRouter(prefix="/reports", tags=["approvers"])


def _report_for_assignment(db: Session, report_id: int, actor: User) -> ExpenseReport:
    report = db.get(ExpenseReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    # The owner routes their own report; approvers can also route anyone's, since they
    # are the ones who know who should look at it.
    if report.owner_id != actor.id and not actor.is_approver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only assign approvers to your own reports.",
        )
    return report


@router.get("/{report_id}/approvers", response_model=list[UserSummary])
def list_approvers(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    report = db.get(ExpenseReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    if not current_user.is_approver and report.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own expense reports.",
        )
    return report.approvers


@router.post(
    "/{report_id}/approvers", response_model=list[UserSummary], status_code=status.HTTP_201_CREATED
)
def assign_approver(
    report_id: int,
    payload: AssignApproverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    report = _report_for_assignment(db, report_id, current_user)

    approver = db.get(User, payload.approver_id)
    if approver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if approver.role is not UserRole.approver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{approver.full_name} does not hold the approver role.",
        )

    already_assigned = db.scalar(
        select(ReportApprover).where(
            ReportApprover.report_id == report_id,
            ReportApprover.approver_id == approver.id,
        )
    )
    # Assigning twice is a no-op rather than an error — the caller's intent is already
    # satisfied, and the composite primary key would reject the duplicate anyway.
    if already_assigned is None:
        db.add(ReportApprover(report_id=report_id, approver_id=approver.id))
        db.commit()

    db.refresh(report)
    return report.approvers


@router.delete("/{report_id}/approvers/{approver_id}", response_model=list[UserSummary])
def unassign_approver(
    report_id: int,
    approver_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    report = _report_for_assignment(db, report_id, current_user)

    assignment = db.scalar(
        select(ReportApprover).where(
            ReportApprover.report_id == report_id,
            ReportApprover.approver_id == approver_id,
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That approver is not assigned."
        )

    # Removing an assignment never touches history: decisions this approver already made
    # stay in the timeline.
    db.delete(assignment)
    db.commit()
    db.refresh(report)
    return report.approvers
