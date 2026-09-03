"""Database engine and per-request session.

Sync SQLAlchemy on purpose: this app has no workload that benefits from async database
access, and the sync path is considerably less fiddly (see docs/decisions.md).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # free-tier databases drop idle connections
    future=True,
    # Without this, a request against an unreachable database blocks until the OS-level
    # TCP timeout — which makes a health check hang for minutes instead of reporting a
    # problem. Fail fast and let the caller see the failure.
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
