from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.schemas.alert import StaleAlertOut, StaleAlertsOut
from app.schemas.report import ReportOut
from app.services import alerts as alerts_service
from app.services.totals import totals_for

router = APIRouter(tags=["alerts"])


@router.get("/alerts/stale", response_model=StaleAlertsOut)
def stale_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StaleAlertsOut:
    """Reports stuck in Submitted for too long. `count` drives the badge in the nav."""
    rows = alerts_service.stale_reports(db, current_user)
    totals = totals_for(db, [report.id for report, _, _ in rows])

    items = []
    for report, days_waiting, dismissible in rows:
        report.total = totals.get(report.id, 0)
        items.append(
            StaleAlertOut(
                report=ReportOut.model_validate(report),
                days_waiting=days_waiting,
                can_dismiss=dismissible,
            )
        )

    return StaleAlertsOut(
        count=len(items),
        items=items,
        threshold_days=settings.stale_after_days,
        realert_after_days=settings.stale_realert_after_days,
    )


@router.post("/reports/{report_id}/alerts/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_stale_alert(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Dismissal is per approver and only for reports assigned to them.

    It suppresses the alert for this approver alone — a colleague assigned to the same
    report still sees it — and only until the re-alert window passes.
    """
    if not alerts_service.can_dismiss(db, report_id, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only dismiss alerts for reports assigned to you.",
        )

    alerts_service.dismiss(db, report_id, current_user)
    db.commit()
