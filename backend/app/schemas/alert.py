from pydantic import BaseModel

from app.schemas.report import ReportOut


class StaleAlertOut(BaseModel):
    report: ReportOut
    days_waiting: int
    # Only an approver assigned to this report may dismiss its alert.
    can_dismiss: bool


class StaleAlertsOut(BaseModel):
    count: int  # drives the nav badge
    items: list[StaleAlertOut]
    threshold_days: int
    realert_after_days: int
