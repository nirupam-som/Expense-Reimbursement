from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportApprover(Base):
    """Many-to-many: which approvers a report is routed to.

    Assignment decides whose queue a report appears in. It is deliberately NOT an
    authorization gate — decision authority is "approver role, and not the owner",
    checked at transition time (docs/decisions.md, Decision 6).
    """

    __tablename__ = "report_approvers"
    __table_args__ = (
        # Reverse direction: "every report assigned to this approver".
        Index("ix_report_approvers_approver_id", "approver_id"),
    )

    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expense_reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    approver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
