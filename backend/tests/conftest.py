"""Test fixtures.

Tests run against a real, disposable PostgreSQL database rather than SQLite, because the
things most worth testing here are Postgres-specific: enum columns, NUMERIC money,
date_trunc week bucketing, and the triggers that make history immutable. A SQLite stand-in
would pass while the real database behaved differently.

The schema is built by running the actual migrations, so the migrations are covered too.
"""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers metadata)
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models import User
from app.models.enums import UserRole

TEST_DB_NAME = "expense_reimbursement_test"

TABLES = (
    "report_comments",
    "report_events",
    "stale_alert_dismissals",
    "report_approvers",
    "expense_lines",
    "expense_reports",
    "users",
)


def _url_for(database: str) -> str:
    return settings.database_url.rsplit("/", 1)[0] + f"/{database}"


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(_url_for("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    test_url = _url_for(TEST_DB_NAME)

    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(alembic_config, "head")

    test_engine = create_engine(test_url)
    yield test_engine
    test_engine.dispose()

    admin = create_engine(_url_for("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(engine) -> Session:
    # TRUNCATE rather than DELETE: the history tables refuse row-level deletes by design.
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session


@pytest.fixture
def client(db) -> TestClient:
    fastapi_app.dependency_overrides[get_db] = lambda: db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


# ----------------------------------------------------------------------------------
# Convenience builders
# ----------------------------------------------------------------------------------

PASSWORD = "password123"


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role: UserRole = UserRole.employee, name: str | None = None) -> User:
        counter["n"] += 1
        index = counter["n"]
        user = User(
            email=f"user{index}@example.com",
            full_name=name or f"User {index}",
            password_hash=hash_password(PASSWORD),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def employee(make_user) -> User:
    return make_user(UserRole.employee, "Employee One")


@pytest.fixture
def approver(make_user) -> User:
    return make_user(UserRole.approver, "Approver One")


@pytest.fixture
def auth(client):
    """Returns a callable producing an Authorization header for a given user."""

    def _auth(user: User) -> dict[str, str]:
        response = client.post(
            "/auth/login", json={"email": user.email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth


@pytest.fixture
def make_report(client, auth):
    """Creates a report (optionally with lines) as its owner, via the API."""

    def _make(owner: User, title: str = "Trip", lines: list[dict] | None = None) -> dict:
        headers = auth(owner)
        response = client.post(
            "/reports",
            json={
                "title": title,
                "date_range_start": "2026-08-01",
                "date_range_end": "2026-08-05",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        report = response.json()

        for line in lines if lines is not None else [
            {
                "expense_date": "2026-08-02",
                "amount": "100.00",
                "category": "travel",
                "description": "Flight",
            }
        ]:
            line_response = client.post(
                f"/reports/{report['id']}/lines", json=line, headers=headers
            )
            assert line_response.status_code == 201, line_response.text

        return report

    return _make
