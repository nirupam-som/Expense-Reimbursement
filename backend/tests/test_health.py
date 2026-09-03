"""Smoke test: proves the app builds and serves requests.

Deliberately does not touch the database — /health/db is exercised manually and by the
deployment's readiness check, so the test suite stays runnable without a live Postgres.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_documented():
    spec = client.get("/openapi.json").json()

    assert "/health" in spec["paths"]
