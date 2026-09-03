from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.dashboard import DashboardOut
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardOut:
    """Headline numbers, status and category breakdowns, and 8 weeks of payments.

    One endpoint rather than four, because the UI always renders them together and
    splitting them would just mean four round trips for one screen.
    """
    return DashboardOut(**build_dashboard(db, current_user))
