"""Expense lines (goal 3).

Lines are editable only while their report is a Draft. That rule depends on another
table's current state, so it is checked here in the application rather than expressed as a
constraint on expense_lines itself.

Note what is absent: no endpoint accepts a report total. The total is always SUM(lines),
computed on read, so there is no writable field for a client to set.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ExpenseLine, ExpenseReport, User
from app.models.enums import ReportStatus
from app.schemas.report import LineCreate, LineOut, LineUpdate

router = APIRouter(prefix="/reports", tags=["expense lines"])


def _editable_report(db: Session, report_id: int, actor: User) -> ExpenseReport:
    report = db.get(ExpenseReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if report.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the report's owner can change its expense lines.",
        )

    if report.status is not ReportStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expense lines can only be changed while the report is a Draft; this "
            f"report is {report.status.value}.",
        )

    return report


@router.get("/{report_id}/lines", response_model=list[LineOut])
def list_lines(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExpenseLine]:
    report = db.get(ExpenseReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    if not current_user.is_approver and report.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own expense reports.",
        )
    return report.lines


@router.post("/{report_id}/lines", response_model=LineOut, status_code=status.HTTP_201_CREATED)
def add_line(
    report_id: int,
    payload: LineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpenseLine:
    _editable_report(db, report_id, current_user)

    line = ExpenseLine(report_id=report_id, **payload.model_dump())
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


@router.patch("/{report_id}/lines/{line_id}", response_model=LineOut)
def update_line(
    report_id: int,
    line_id: int,
    payload: LineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpenseLine:
    _editable_report(db, report_id, current_user)

    line = db.get(ExpenseLine, line_id)
    if line is None or line.report_id != report_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Expense line not found."
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, field, value)

    db.commit()
    db.refresh(line)
    return line


@router.delete("/{report_id}/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line(
    report_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _editable_report(db, report_id, current_user)

    line = db.get(ExpenseLine, line_id)
    if line is None or line.report_id != report_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Expense line not found."
        )

    db.delete(line)
    db.commit()
