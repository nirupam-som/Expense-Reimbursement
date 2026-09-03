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

## Decision 5 — Immutability enforced by database grants, not only by missing routes

- **Chose:** No `PATCH`/`DELETE` routes for history tables, **and** the application's database
  role has no `UPDATE`/`DELETE` privilege on `report_events` or `report_comments`.
- **Rejected:** Relying on the application simply not offering an edit path.
- **Why:** Goal 9 says nothing in the timeline can be edited or deleted after the fact,
  *including by approvers*. "We didn't build a route for it" is a promise about today's code; a
  revoked grant holds even if a future refactor adds one by mistake. This only works because
  migrations run under a different, more privileged role than the app connects with — noted in
  `docs/schema.md`, since the two-role setup is the thing that makes the guarantee real.

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

*(A later-reversed decision will be recorded here, with a **Later reversed:** line on whichever
entry it turns out to be, once the build produces one.)*
