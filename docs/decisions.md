# Decisions

Decisions that actually shaped this codebase — where a real alternative existed and one was
chosen. At least one entry is a decision later reversed.

## Decision 1 — Sync SQLAlchemy, not async

- **Chose:** Sync SQLAlchemy 2.x with `psycopg` 3, called from FastAPI's threadpool.
- **Rejected:** `async` SQLAlchemy with `asyncpg` and async route handlers.
- **Why:** FastAPI being async-capable is not a reason for the database layer to be. This app
  has no workload where async database access wins anything — no long-lived connections, no
  high-concurrency fan-out, a handful of demo users. Async SQLAlchemy costs real setup and
  debugging time (session lifecycle, greenlet errors, no sync fallbacks in libraries) and would
  have bought nothing measurable at this scale. Time saved here went into the transition rules
  instead.

## Decision 2 — JWT bearer tokens, not session cookies

- **Chose:** Stateless JWT sent as `Authorization: Bearer <token>`.
- **Rejected:** Server-side sessions in a cookie.
- **Why:** The frontend and API are deployed to two different origins (Vercel and Render).
  Cookie-based auth across origins means `SameSite=None`, `Secure`, `allow_credentials`, and a
  matching exact-origin CORS list — several places to get subtly wrong, all of which fail only
  in the deployed environment and not locally. A bearer header sidesteps all of it. The
  trade-off accepted: no server-side revocation, so a stolen token is valid until it expires.
  For a demo system with seeded credentials, that is an acceptable exposure; for real payroll
  data it would not be.

## Decision 3 — Report totals computed on read, never stored

- **Chose:** `SUM(expense_lines.amount)` computed at query time. There is no `total_amount`
  column on `expense_reports`.
- **Rejected:** A cached `total_amount` column kept in sync by a trigger or by application code
  on every line insert/update/delete.
- **Why:** Goal 3 requires the total to always equal the sum of its lines. A stored copy can
  drift from the lines it summarises; a computed value cannot. The cached column also adds a
  second surface to protect from client writes, on top of the lines themselves. The cost is a
  `SUM` per report read, which is measurable only at a scale this project does not have — and
  it is documented in `docs/schema.md` as one of the first things to revisit at 100x data.

## Decision 4 — One `can_transition` function, called by every path including bulk

- **Chose:** A single `can_transition(report, action, actor) -> (allowed, reason)` function that
  the single-report endpoints and each iteration of the bulk endpoints both call.
- **Rejected:** Per-endpoint permission checks, with the bulk endpoints implementing their own
  batch-level validation.
- **Why:** The self-approval rule appears in four places in the brief (approve, reject,
  mark-paid, and inside bulk actions). Four implementations of one rule is four chances for them
  to disagree — and the bulk endpoint is specifically required to report *why* each report was
  refused, naming self-ownership distinctly. Sharing one function is what makes the bulk result
  and the single-report 403 provably consistent: they are the same call.

## Decision 5 — Immutability enforced by the database, not only by missing routes

- **Chose:** No `PATCH`/`DELETE` routes for history tables, **and** a `BEFORE UPDATE OR DELETE`
  trigger on `report_events` and `report_comments` that raises an exception.
- **Rejected:** Relying on the application simply not offering an edit path.
- **Why:** Goal 9 says nothing in the timeline can be edited or deleted after the fact,
  *including by approvers*. "We didn't build a route for it" is a promise about today's code; a
  database-level refusal holds even if a future refactor adds one by mistake.

- **Later reversed:** the database half of this started as `REVOKE UPDATE, DELETE ON
  report_events, report_comments`, and that is what `docs/architecture.md` and `docs/schema.md`
  originally said. Writing the migration is what changed my mind: a `REVOKE` does not bind the
  table's *owner*, and it only would have meant anything if migrations ran as one role while the
  application connected as a second, less privileged one. The free hosting tiers this deploys to
  hand you a single role and encourage using it for everything — so the guarantee I had written
  down would have been decorative in exactly the environment it shipped to, while still reading
  as though it were airtight. A trigger holds for every non-superuser regardless of how roles are
  configured, so I swapped to that and wrote a test that runs raw SQL `UPDATE` and `DELETE`
  against both tables to prove the refusal is real rather than assumed. The cost is that
  `TRUNCATE` still bypasses it (triggers are per-row), which is what the seed script relies on to
  reset a demo database — an administrative path the application itself cannot reach.

## Decision 7 — Rejection returns the report to Draft, and writes two history rows

- **Chose:** Rejecting writes `submitted → rejected` (carrying the reason) *and*
  `rejected → draft` in one transaction, leaving the report in Draft.
- **Rejected:** Leaving the report in a `rejected` status that behaves like a draft.
- **Why:** The brief says both things — that a report moves to *Rejected*, and that "the report
  then returns to Draft, where its owner can edit it and submit it again". A single status cannot
  satisfy both. Two rows do: the rejection and its reason stay permanently visible in the
  timeline, while the report is immediately editable again with no special-case "rejected is
  really a draft" logic anywhere. The visible trade-off is that the dashboard's status breakdown
  never shows a standing "rejected" count, because rejected reports genuinely are drafts again —
  the history is where rejections live.

## Decision 8 — `submitted_at` is cleared on rejection, and dismissals are dropped on resubmission

- **Chose:** Rejection sets `submitted_at` back to `NULL`; submitting deletes any
  `stale_alert_dismissals` rows for that report.
- **Rejected:** Leaving both alone as historical facts.
- **Why:** Both feed the stale-alert query, and leaving them would produce wrong alerts rather
  than merely untidy data. A rejected report is not awaiting a decision, so it must not age
  towards an alert; and a *new* submission deserves a clean slate, otherwise an approver's
  dismissal from a previous round silently suppresses the alert for a resubmission they have
  never seen. The audit trail is unaffected — the real submission history lives in
  `report_events`, which is what makes it safe to treat these two columns as current state
  rather than as history.

## Decision 6 — Approver assignment routes work, it does not gate authority

- **Chose:** Assignment (`report_approvers`) determines whose queue a report appears in. Any
  approver who does not own a report may decide on it.
- **Rejected:** Treating assignment as an authorization boundary, where only assigned approvers
  can approve or reject.
- **Why:** The brief is genuinely ambiguous here. Goal 5 asks for assignment and an
  "assigned to me" filter; Goal 4 states the decision rule as "a user with the approver role,
  who does not own the report" — with no mention of assignment. Reading assignment as routing
  keeps the two goals consistent as written, and avoids a deadlock where a report whose only
  assigned approver is its owner can never be decided at all. The alternative reading is
  defensible; this one is documented rather than left implicit.

## Decision 9 — Tests run against a real Postgres, not SQLite

- **Chose:** A disposable `expense_reimbursement_test` database, created per test session and
  built by running the actual Alembic migrations.
- **Rejected:** SQLite in-memory for speed.
- **Why:** Almost everything worth testing here is Postgres-specific — native enum columns,
  `NUMERIC` money, `date_trunc('week', …)` bucketing for the dashboard, and the triggers that
  make history immutable. On SQLite those either behave differently or do not exist, so the
  suite would have been green while the deployed system misbehaved. Building the schema by
  running the migrations means the migrations are covered too, rather than being the one
  untested part of the system. The cost is a slower suite (~3 minutes) and a hard dependency on
  a running database, which is the right trade for a system whose correctness lives in SQL.
