# AI prompts

The prompts actually used, in order, grouped by what they were trying to achieve — including the
ones that produced bad output and what changed afterwards.

*Filled in as the work happens.*

## Understanding the brief before writing anything

### Prompt

Asked Claude Code to read the assignment README and produce a detailed implementation checklist
covering all ten required goals — for each: required functionality, business rules, what must be
enforced server-side, suggested endpoints and entities, edge cases, and how to test it — plus a
list of requirements that are easy to miss and a practical ~12-hour implementation sequence.
Explicitly instructed it not to write any application code.

### What it produced

A goal-by-goal breakdown that correctly surfaced several things the brief states only in passing:
that the self-approval rule applies to *three* actions (approve, reject, mark-paid) and inside
bulk actions too; that bulk results must name self-ownership refusals distinctly from other
refusals; that a dismissed stale alert has to *reappear*, which a boolean flag cannot express;
and that "any other transition must be rejected with a message explaining why" requires an
explanatory error, not a bare status code.

### What was corrected / verified

It also flagged real ambiguities in the brief rather than silently assuming answers — whether
approver *assignment* gates approval authority, whether an empty report can be submitted, and
whether the category breakdown is by line or by report. Those went into `docs/decisions.md` as
explicit decisions instead of being buried in code. Verified each claimed requirement against the
README text before accepting it into the checklist.

## Choosing the stack

### Prompt

Asked it to evaluate React + FastAPI + PostgreSQL against the assignment — why it fits, the
risks, how to stay inside 12 hours, and which parts should stay simple rather than
over-engineered — with an instruction not to change the stack without a strong reason.

### What it produced

Confirmed the fit (several goals map directly onto plain SQL: the many-to-many assignment table,
server-side search/filter/sort/pagination, dashboard aggregates, and DB-level immutability via
revoked grants). Flagged the real risks: auth is entirely hand-rolled in FastAPI, and the
frontend/backend being on different hosts makes cross-origin cookies a time sink.

### What was corrected

Its instinct to reach for async SQLAlchemy "because FastAPI is async" was pushed back on — sync
SQLAlchemy is the right call at this scale and materially less fiddly. That became
`docs/decisions.md` Decision 1. Also declined the suggestion to pre-install a charting library
and state-management tooling before there were screens to use them.

## Architecture and schema design

### Prompt

Asked for `docs/architecture.md` covering each layer, the request path for one representative
action end to end, where each piece runs, and what would deliberately not be built. Then asked
for the PostgreSQL schema for all ten goals with per-column types/nullability/keys/indexes, the
DB-versus-application constraint split, and an answer to "what would break first at 100x the
data".

### What it produced

The seven-table design in `docs/schema.md`, and the seven-step request walkthrough in
`docs/architecture.md`. Two useful points came out of it: a `CHECK` constraint structurally
*cannot* express the self-approval rule (it cannot see who is making the request), so that rule
necessarily lives in application code; and the revoked-grants immutability guarantee is only real
if migrations run under a different role than the app connects with.

### What was corrected

The implementation phase exposed three specific things the initial design missed, which were then corrected:
1. **Immutability implementation:** The plan to revoke `UPDATE/DELETE` grants was flawed because it doesn't bind the table owner (the role a free-tier deployment uses). This was corrected by using a database trigger instead.
2. **Test data domains:** `email-validator` rejects reserved TLDs (like `@acme.test`), breaking login for seed data. Accounts were switched to `@acme.com`.
3. **Health check reliability:** The `/health/db` endpoint initially had no connect timeout, causing it to hang for 90 seconds instead of failing fast. A timeout was added to ensure deployment readiness probes wouldn't stall.

## Foundation and Database Setup

### Prompt

Asked the AI to write the SQLAlchemy models for the seven tables defined in `docs/schema.md`, including Alembic migration setup and FastAPI dependency injection for the database session. Instructed it to use native PostgreSQL ENUMs for roles and statuses, and `NUMERIC(10, 2)` for currency.

### What it produced

Correctly generated the models and relationships. It set up Alembic and the `get_db` dependency correctly. It also included Pydantic schemas for the initial models.

### What was corrected

It missed the `server_default` for the timestamps in the SQLAlchemy models, relying entirely on Python-side defaults which aren't safe against manual DB inserts. Added `server_default=func.now()` to the models before running the first migration.

## Implementing Lifecycle Rules

### Prompt

Asked to implement the `can_transition()` function as a central service in `services/lifecycle.py`, taking a report, actor, and target action, and returning either success or a specific error message. Provided the exact matrix of allowed transitions and the self-approval rule from the brief.

### What it produced

A solid, centralized state machine function that checks the current status, the requested action, and the user's role. It correctly identified that `reject` requires a reason and forces the report back to `Draft`. 

### What was corrected

It initially forgot to block the owner from approving their own report if they also happen to be an Approver. I had to explicitly prompt it again with: "Remember the self-approval block: an Approver cannot approve, reject, or mark their own report as paid." It then added the `report.owner_id == actor.id` check.

## Immutability via PostgreSQL Triggers

### Prompt

Asked to create an Alembic migration that adds a PostgreSQL trigger to the `report_events` and `comments` tables to entirely reject any `UPDATE` or `DELETE` operations, returning an exception, to fulfill the immutable history requirement.

### What it produced

It wrote a correct PL/pgSQL function that raises an exception `RAISE EXCEPTION 'History is immutable'` and attached it as a `BEFORE UPDATE OR DELETE` trigger to both tables.

### What was corrected

The migration down-revision (downgrade) logic it wrote dropped the trigger but forgot to drop the PL/pgSQL function itself. I added the `DROP FUNCTION` statement to keep the database clean on rollbacks.

## Complex SQL for Dashboard and Search

### Prompt

Asked to write the server-side logic for Goal 6 (Finding) and Goal 8 (Dashboard). For finding, needed title search, status/owner/approver filters, sorting, and offset pagination in `services/reports_query.py`. For the dashboard, needed 4 headline stats, category breakdown, and 8-week payment chart data in `services/dashboard.py`.

### What it produced

It leveraged SQLAlchemy 2.0 `select()` constructs elegantly. For the 8-week chart, it used `date_trunc('week', ...)` successfully to group the payments.

### What was corrected

For the dashboard, it didn't zero-fill missing weeks in the 8-week chart. If a week had no payments, it just omitted it from the JSON response. I had to prompt it to "Generate a sequence of the last 8 weeks in Python and left-join the database results onto it so every week has a guaranteed `0` if missing."

## Building the React Frontend

### Prompt

Asked to scaffold the React frontend using Vite, creating screens for Login, Dashboard, Report List (with filters), and Report Detail. Instructed it to use plain CSS and plain `fetch` without any heavy state management libraries like Redux.

### What it produced

A clean, multi-page layout using React Router. The API client wrapper properly injected the JWT token into the `Authorization` header for every request and handled 401s by redirecting to Login.

### What was corrected

It tried to conditionally render the "Approve" and "Reject" buttons based solely on whether the user's role was `Approver`. I had to remind it that an Approver cannot approve their *own* report, so the UI should ideally hide or disable the button if `report.owner_id === currentUser.id`.
