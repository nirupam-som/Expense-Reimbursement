# Expense Reimbursement

Replaces the "email a spreadsheet to your manager" reimbursement workflow: employees submit
expense reports with line items, an approver who is *not* the employee decides on them, and
finance can see exactly what is owed and to whom at any moment.

Take-home assignment 11. The ten required goals and how this system meets them are tracked in
[SUBMISSION.md](SUBMISSION.md).

## Stack

| Layer | Choice |
|---|---|
| Frontend | React 18 + Vite + React Router (plain CSS, no component library) |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.x (sync), Alembic migrations |
| Database | PostgreSQL 16 |
| Auth | JWT bearer tokens (`Authorization: Bearer <token>`) |

Rationale, trade-offs and what was deliberately left out are in [docs/](docs/).

## Layout

```
backend/          FastAPI service — owns every business rule
  app/
    api/routes/   HTTP endpoints
    core/         config (env-driven settings)
    db/           engine, session, declarative base
    models/       SQLAlchemy ORM models
    schemas/      Pydantic request/response models
    services/     business logic (lifecycle transitions, aggregation)
  alembic/        database migrations
frontend/         React SPA — presentation only, trusts the server for every fact
docs/             architecture, schema, plan, decisions, AI prompts
```

## Running locally

Three processes: database, backend, frontend.

### 1. Database

```bash
docker compose up -d db
```

Runs Postgres 16 on `localhost:5432` (user `expense`, password `expense`, database
`expense_reimbursement`). Any other Postgres works too — just point `DATABASE_URL` at it.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env          # cp on macOS/Linux
alembic upgrade head            # apply migrations
uvicorn app.main:app --reload
```

API on http://localhost:8000 — interactive docs at http://localhost:8000/docs.

### 3. Frontend

```bash
cd frontend
npm install
copy .env.example .env          # cp on macOS/Linux
npm run dev
```

App on http://localhost:5173.

## Environment variables

Nothing secret is committed. See `backend/.env.example` and `frontend/.env.example` for the full
list; the ones that matter:

| Variable | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | Postgres connection string |
| `JWT_SECRET` | backend | signing key for auth tokens — must be set to a real secret in production |
| `CORS_ORIGINS` | backend | comma-separated list of allowed frontend origins |
| `STALE_AFTER_DAYS` | backend | how long a Submitted report waits before it raises a stale alert |
| `STALE_REALERT_AFTER_DAYS` | backend | how long a dismissed stale alert stays dismissed |
| `VITE_API_BASE_URL` | frontend | base URL of the backend API |

## Tests

```bash
cd backend
pytest
```
