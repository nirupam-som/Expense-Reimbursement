from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ExpenseCategory


class ExpenseLine(Base):
    """One line item on a report. Editable only while the report is in Draft."""

    __tablename__ = "expense_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_line_amount_positive"),
        CheckConstraint("length(btrim(description)) > 0", name="ck_expense_line_has_description"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expense_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expense_date: Mapped[date] = mapped_column("expense_date", Date, nullable=False)
    # NUMERIC, never float: currency has to reconcile to the cent.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        Enum(
            ExpenseCategory,
            name="expense_category",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    report: Mapped["ExpenseReport"] = relationship(back_populates="lines")  # noqa: F821
