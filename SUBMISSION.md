# Submission

## Links

- **GitHub repository:** <public repo URL — to be added>
- **Live application:** <deployed URL — to be added>

## Notes for the reviewer

<To be filled in before submitting — including whether the host sleeps when idle and the first
request can take up to a minute.>

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Employee | | |
| Approver | | |

## Stack

| Layer | What you used | Why |
|-------|---------------|-----|
| Frontend | React 18 + Vite + React Router | Fastest to build in; the UI is ~5 screens and needs no more than routing and component state |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.x (sync), Alembic | Pydantic makes the API's validation boundary explicit; dependency injection is a clean home for the role + ownership checks every goal depends on |
| Database | PostgreSQL 16 | Several goals map straight onto SQL — many-to-many assignment, server-side search/sort/pagination, dashboard aggregates, and DB-level history immutability via revoked grants |
| Hosting | <to be added> | |

## Goal checklist

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Not done | |
| 2 | Expense reports | Not done | |
| 3 | Expense lines | Not done | |
| 4 | Report lifecycle with rules | Not done | |
| 5 | Assigned approvers | Not done | |
| 6 | Server-side finding/search/filter/sort/pagination | Not done | |
| 7 | Bulk actions and CSV export | Not done | |
| 8 | Dashboard | Not done | |
| 9 | Immutable history/timeline | Not done | |
| 10 | Stale-approval alerts | Not done | |

## How much time did you actually spend?

<To be filled in.>

## What would you do next, with another 12 hours?

<To be filled in.>

## What are you least happy with in this codebase, and why?

<To be filled in.>
