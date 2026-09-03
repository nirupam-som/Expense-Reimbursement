"""Liveness and readiness checks.

Split in two on purpose: /health answers without touching the database (so a hosting
platform's health check does not fail just because the database is briefly unreachable),
while /health/db is the one that actually proves the connection works.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # 503 rather than a 500 traceback: an unreachable database is a known
        # operational state, not an unexpected bug, and the caller should be told so.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unreachable: {exc.__class__.__name__}",
        ) from exc

    return {"status": "ok", "database": "reachable"}
