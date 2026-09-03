"""Append-only history. Nothing here is ever updated or deleted.

Two layers protect that (docs/schema.md, "How immutable history is protected"):
no API route mutates these tables, and the application's database role is granted
INSERT/SELECT only — the UPDATE/DELETE grants are revoked by a migration.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReportStatus

_status_enum = Enum(
    ReportStatus,
    name="report_status",
    values_callable=lambda e: [m.value for m in e],
    create_type=False,  # the type is created once, by expense_reports
)


class ReportEvent(Base):
    """One row per status transition. Every row is a real change of state."""

    __tablename__ = "report_events"
    __table_args__ = (Index("ix_report_events_report_id_created_at", "report_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: history must keep saying who acted, even if users are
    # ever removable. Losing attribution silently would defeat the point of an audit trail.
    actor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[ReportStatus] = mapped_column(_status_enum, nullable=False)
    to_status: Mapped[ReportStatus] = mapped_column(_status_enum, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    actor: Mapped["User"] = relationship()  # noqa: F821


class ReportComment(Base):
    """A comment from the report's owner or an approver. Also append-only."""

    __tablename__ = "report_comments"
    __table_args__ = (
        CheckConstraint("length(btrim(body)) > 0", name="ck_report_comment_not_empty"),
        Index("ix_report_comments_report_id_created_at", "report_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    author: Mapped["User"] = relationship()  # noqa: F821
