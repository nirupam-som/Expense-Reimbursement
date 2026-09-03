from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ExpenseCategory, ReportStatus


class StatusBreakdown(BaseModel):
    status: ReportStatus
    count: int


class CategoryBreakdown(BaseModel):
    category: ExpenseCategory
    total: Decimal
    line_count: int


class WeeklyPaid(BaseModel):
    week_start: date
    total: Decimal


class DashboardOut(BaseModel):
    awaiting_approval: int
    # Sum of every Approved-but-not-yet-Paid report. Comes from the same query as the
    # CSV export, so the headline figure and the exported file can never disagree.
    total_due: Decimal
    approved_this_week: int
    paid_this_week: int
    by_status: list[StatusBreakdown]
    by_category: list[CategoryBreakdown]
    weekly_paid: list[WeeklyPaid]  # exactly 8 entries, zero-filled
