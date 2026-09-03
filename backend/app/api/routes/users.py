from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.user import UserSummary

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserSummary])
def list_users(
    role: UserRole | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    """Directory used to populate owner/approver filters and the assignment picker.

    Returns names and roles only — no password hashes, no per-user financial data — so it
    is safe for any signed-in user to read.
    """
    stmt = select(User).order_by(User.full_name)
    if role is not None:
        stmt = stmt.where(User.role == role)

    return list(db.scalars(stmt).all())
