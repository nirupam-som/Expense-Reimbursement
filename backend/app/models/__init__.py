"""SQLAlchemy ORM models. Design and rationale in docs/schema.md.

Every model is imported here so that `import app.models` registers the full metadata —
Alembic's autogenerate and Base.metadata.create_all both depend on that.
"""

from app.models.alert import StaleAlertDismissal
from app.models.approver import ReportApprover
from app.models.enums import ExpenseCategory, ReportStatus, UserRole
from app.models.history import ReportComment, ReportEvent
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.user import User

__all__ = [
    "ExpenseCategory",
    "ExpenseLine",
    "ExpenseReport",
    "ReportApprover",
    "ReportComment",
    "ReportEvent",
    "ReportStatus",
    "StaleAlertDismissal",
    "User",
    "UserRole",
]
