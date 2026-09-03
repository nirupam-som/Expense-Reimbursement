from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ExpenseCategory, ReportStatus
from app.schemas.user import UserSummary


class LineCreate(BaseModel):
    expense_date: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: ExpenseCategory
    description: str = Field(min_length=1, max_length=500)


class LineUpdate(BaseModel):
    expense_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category: ExpenseCategory | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_date: date
    amount: Decimal
    category: ExpenseCategory
    description: str


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date_range_start: date
    date_range_end: date

    @model_validator(mode="after")
    def check_range(self) -> "ReportCreate":
        if self.date_range_end < self.date_range_start:
            raise ValueError("date_range_end must be on or after date_range_start")
        return self


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    date_range_start: date | None = None
    date_range_end: date | None = None


class ReportOut(BaseModel):
    """A report in a list. `total` is computed by the server from its lines — there is no
    stored total column, and no client-supplied total is ever accepted."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    date_range_start: date
    date_range_end: date
    status: ReportStatus
    is_archived: bool
    submitted_at: datetime | None
    decided_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
    owner: UserSummary
    total: Decimal


class ReportDetailOut(ReportOut):
    lines: list[LineOut]
    approvers: list[UserSummary]


class ReportPageOut(BaseModel):
    items: list[ReportOut]
    total: int  # total matches across every page, not just this one
    page: int
    page_size: int


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AssignApproverRequest(BaseModel):
    approver_id: int
