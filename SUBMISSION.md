# Submission

## Links

- **GitHub repository:** <public repo URL — to be added>
- **Live application:** <deployed URL — to be added>

## Notes for the reviewer

- **Demo data is seeded** with a deliberate spread: reports in every status, payments across the
  last eight weeks so the dashboard chart has a shape, two reports stale enough to raise alerts,
  a rejected report that returned to Draft with its rejection still in the timeline, and **an
  approver's own submitted report** — sign in as Priya and try to approve "Approver's own trip —
  Vienna" to see the self-approval rule refuse it.
- **Free tiers sleep when idle.** The first request after a quiet period can take up to a minute
  to wake. A slow first load is not a broken deployment.
- To reset the demo data at any time: `python -m app.seed` in `backend/`.

## Demo credentials

Password for every account: `password123`

| Role | Email | Notes |
|------|-------|-------|
| Approver | priya@acme.com | Also owns a submitted report she cannot approve herself |
| Approver | daniel@acme.com | Assigned to several reports |
| Employee | aisha@acme.com | Reports in several states |
| Employee | marco@acme.com | Has a report approved and awaiting payment |
| Employee | lena@acme.com | Has a draft in progress |
| Employee | tom@acme.com | Owns the rejected-and-redrafted report |

## Stack

| Layer | What you used | Why |
|-------|---------------|-----|
| Frontend | React 18 + Vite + React Router, plain CSS | ~5 screens; routing and component state are enough, and a state library or design system would have been more machinery than the problem needs |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.x (sync), Alembic | Pydantic makes the validation boundary explicit; dependency injection is a natural home for the role + ownership checks nearly every goal depends on |
| Database | PostgreSQL 16 | Several goals map straight onto SQL — many-to-many assignment, server-side search/sort/pagination, dashboard aggregates — and triggers give history immutability a real guarantee rather than a promise |
| Hosting | <to be added> | |

## Goal checklist

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Email + password, JWT bearer tokens. Role *and* ownership checked server-side on every route; employees are scoped at the query level, so a filter parameter can narrow what they see but never widen it |
| 2 | Expense reports | Done | Owner-only create/edit, editable in Draft only. Archive/restore is a flag orthogonal to status — it never touches lifecycle or history |
| 3 | Expense lines | Done | Date, amount, fixed category enum, description. Editable until submitted. Totals are always `SUM(lines)` computed on read — there is no stored total column for a client to set |
| 4 | Report lifecycle with rules | Done | One `can_transition()` governs every status change. Rejection requires a reason and returns the report to Draft while keeping the rejection in the timeline. Every illegal transition is refused with a message saying why; the full state × action matrix is tested |
| 5 | Assigned approvers | Done | Many-to-many. Full queue plus an "assigned to me" filter. Assignment routes work but is not an authorization gate — documented as Decision 6 |
| 6 | Server-side finding | Done | Title search, status/owner/approver filters, sort by submitted date/status/total, `LIMIT`/`OFFSET` pagination with a true total-match count. All in SQL; the sort key is an allow-list |
| 7 | Bulk actions and CSV export | Done | Each report checked individually against the same `can_transition`; the response names reports refused *because the approver owns them* separately from other refusals. CSV export of approved-but-unpaid, from the same query as the dashboard's "total due" |
| 8 | Dashboard | Done | Four headline numbers, status and category breakdowns, and 8 zero-filled weeks of payments. Week counts come from the event log, so a report approved and paid in the same week counts in both |
| 9 | Immutable history/timeline | Done | Status changes and comments, with actor and rejection reason. No route mutates them, **and** a database trigger refuses `UPDATE`/`DELETE` — proven by a test that tries raw SQL |
| 10 | Stale-approval alerts | Done | Computed live, no background job. Dismissal is per approver and stored as a timestamp, so the alert returns by itself after the re-alert window. Resubmitting clears old dismissals |

**Not built:** the optional LangChain rejection-reason assistant designed in
`docs/architecture.md`, and every stretch idea from the brief. The ten goals came first.

## Tests

`cd backend && pytest` — 85 tests against a disposable PostgreSQL database, built by running the
real migrations. Weighted towards the rule-dense parts: the full transition matrix, self-approval
across all three decision actions and inside bulk, server-computed totals, query scoping, CSV
contents, dashboard arithmetic, and the alert reappearance cycle.

## How much time did you actually spend?

<To be filled in.>

## What would you do next, with another 12 hours?

1. **Keyset pagination and a trigram index on `title`** — the two things `docs/schema.md`
   identifies as breaking first at 100× the data, and both are small changes.
2. **Make the self-approval rule visible earlier.** Right now an approver only learns they cannot
   decide on their own report when the queue refuses it. Filtering their own reports out of the
   decide-eligible queue by default would be kinder, with a toggle to see them.
3. **Optimistic concurrency on decisions.** Two approvers acting on the same report at the same
   moment currently resolve by whoever commits first; the loser gets a "wrong status" refusal,
   which is correct but reads like a bug to the person who sees it.
4. **The LangChain rejection-reason assistant**, which is designed but deliberately unbuilt.

## What are you least happy with in this codebase, and why?

**The frontend has no tests.** The backend is well covered, and the rules that matter live there —
but the React app has real logic in it (which actions to offer for a given status and viewer,
how bulk results are summarised) that is currently only verified by me clicking through it. If
the UI offers a button the server then refuses, the user sees an error where they should have
seen nothing at all. It is the part of the system most likely to regress silently.

Second: **`_serialise()` in `app/api/routes/reports.py` attaches `total` onto the ORM instance**
before validating it. It is concise and it works, but it mutates an object that otherwise
represents a database row, which is the kind of cleverness that confuses whoever reads it next.
An explicit constructor would be duller and better.
