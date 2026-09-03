from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReportStatus


class ExpenseReport(Base):
    """An expense report owned by exactly one employee.

    Note there is no `total` column: a report's total is always SUM(lines.amount),
    computed at read time so it can never drift from the lines it summarises
    (docs/decisions.md, Decision 3).
    """

    __tablename__ = "expense_reports"
    __table_args__ = (
        CheckConstraint(
            "date_range_end >= date_range_start", name="ck_report_date_range_ordered"
        ),
        # Serves the stale-alert query (submitted + submitted_at cutoff) and the
        # "sort by submitted date" case in the report list.
        Index("ix_expense_reports_status_submitted_at", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    date_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_range_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            name="report_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReportStatus.draft,
        server_default=ReportStatus.draft.value,
        index=True,
    )
    # Archiving is orthogonal to status: it hides a report from default views without
    # touching its lifecycle or its history.
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(  # noqa: F821
        back_populates="reports", foreign_keys=[owner_id]
    )
    lines: Mapped[list["ExpenseLine"]] = relationship(  # noqa: F821
        back_populates="report", cascade="all, delete-orphan", order_by="ExpenseLine.expense_date"
    )
    approvers: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary="report_approvers", viewonly=True
    )
