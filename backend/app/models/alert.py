from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaleAlertDismissal(Base):
    """Per-approver dismissal of a stale-approval alert.

    Deliberately mutable, unlike the history tables: re-dismissing a reappeared alert
    upserts `dismissed_at` rather than appending a row. Goal 9's immutability applies to
    a report's status/comment history, not to alert bookkeeping.

    A timestamp rather than a boolean, because the alert has to come back on its own
    STALE_REALERT_AFTER_DAYS later — a flag would need a job to clear it.
    """

    __tablename__ = "stale_alert_dismissals"
    __table_args__ = (Index("ix_stale_alert_dismissals_approver_id", "approver_id"),)

    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expense_reports.id", ondelete="CASCADE"), primary_key=True
    )
    approver_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
