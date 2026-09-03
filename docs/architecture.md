# Architecture

Stack: React (frontend) + FastAPI (backend/API) + PostgreSQL (database), JWT-based auth.
This document describes the design before implementation, so it doubles as the plan we build
against. It will be revisited once the system has taken real shape, per the sections that still
need it.

## Moving pieces, and how they talk to each other

```
┌─────────────────┐        HTTPS / JSON            ┌───────────────────┐        SQL (psycopg)      ┌──────────────┐
│   React SPA      │  ───────────────────────────▶ │   FastAPI app      │  ───────────────────────▶ │  PostgreSQL   │
│   (Vercel)        │  ◀─────────────────────────  │   (Render)         │  ◀───────────────────────  │  (Supabase)   │
└─────────────────┘   Bearer <JWT> on every call    └───────────────────┘   SQLAlchemy sessions      └──────────────┘
```

Three pieces, three separate free-tier hosts, one communication path each:

- **Frontend — React SPA.** A single-page app (Vite + React + React Router). Owns nothing but
  presentation and client-side navigation; every fact it displays (totals, status, permissions)
  is fetched from the API, never computed locally. Talks to the backend exclusively over HTTPS
  with JSON request/response bodies.
- **Backend/API — FastAPI.** A single Python service exposing a REST API. Owns all business
  rules: authentication, authorization, validation, the report lifecycle, bulk-action semantics,
  aggregation for the dashboard, CSV generation, and stale-alert computation. This is the only
  piece that talks to the database.
- **Database — PostgreSQL.** Owns durable state and a handful of constraints that are cheaper
  and safer to guarantee at this layer than in application code (see Validation, and Immutable
  history below). No other component connects to it directly.

**Where each piece runs:**

| Piece | Runs on | Talks to |
|---|---|---|
| React SPA | Vercel (static build, served to the browser) | FastAPI, over the public internet, from the user's browser |
| FastAPI app | Render (a long-running web service process) | PostgreSQL, over a private/managed connection string |
| PostgreSQL | Supabase (managed Postgres) | Only the FastAPI app — never reachable from the browser |

The browser never talks to the database directly, and never talks to Supabase directly — every
read and write is mediated by FastAPI, which is where every rule below is enforced. This is the
one architectural rule everything else in this document depends on: **the client is not
trusted for anything.**

## Authentication

Email + password, JWT-based, stateless on the server.

- Signup hashes the password with `bcrypt` before storing it — plaintext is never written or
  logged. (The `bcrypt` library directly, not via `passlib`: passlib is unmaintained and warns
  against bcrypt 4.x, and only two functions were needed from it.)
- Login verifies the hash and, on success, issues a JWT signed with a server-held secret
  (`HS256`), containing `sub` (user id), `role`, and a short expiry (24h).
- The client sends the token back as `Authorization: Bearer <token>` on every subsequent
  request. No server-side session store — the token itself is the credential, verified on each
  request by re-checking the signature and expiry.
- The frontend keeps the token in `localStorage` and holds the decoded user in memory/React
  state, re-validated via a `GET /auth/me` call on page load rather than trusting a locally
  decoded, unverified copy of the token's claims.
- Chosen over cookie-based sessions specifically because the frontend and backend are two
  different origins on two different hosts (Vercel / Render) — a bearer header sidesteps
  cross-site cookie and `SameSite` configuration entirely.

A FastAPI dependency, `get_current_user`, decodes and verifies the token on every protected
route and loads the corresponding `User` row. Every other piece of authorization below builds on
top of this one dependency.

## Authorization

Two independent checks, both enforced server-side, on every request that touches a report:

1. **Role check** — does this user's role permit this *kind* of action at all? (e.g., only
   `approver` may call `/reports/{id}/approve`.)
2. **Ownership check** — does this *specific* report belong to this user, or is this user
   excluded from acting on it because they own it? (e.g., an approver is blocked from approving,
   rejecting, or marking paid a report where `report.owner_id == current_user.id`, regardless of
   role.)

Both checks live as small, reusable FastAPI dependencies (`require_approver`,
`require_owner_or_visible`, and a `forbid_self_decision` check used specifically by the
lifecycle-transition endpoints), composed per-route rather than reimplemented inline in each
handler. This is deliberate: goals 1, 4, 5 and 7 all restate some form of "not your own report,
even if you hold the role," and it must be the *same* check in every place it applies (single
report, bulk batch, queue visibility) rather than four subtly different re-implementations.

List/search endpoints apply the same authorization as a query-level scope, not a post-fetch
filter: an employee's SQL query has `WHERE owner_id = :current_user_id` built into it; an
approver's does not have that clause, but still excludes rows appropriately per-action (e.g., the
decide-eligible queue still excludes their own reports at the query level for the "assigned to
me" view, if assignment is used as a queue filter — see Approver assignment below).

## Validation

Two layers, each doing a different job:

- **Pydantic request/response models (FastAPI)** — shape and type validation at the API
  boundary: required fields, string lengths, enum membership (expense category, report status
  transitions requested), numeric bounds (amount > 0). This is also how the "total is
  server-computed, never client-set" rule (goal 3) is enforced structurally: the write schema for
  an expense line has no `total` field on the report at all, and the report's `total` in any
  response is a computed/aggregated value, never read from a stored client-writable column.
- **Database constraints (PostgreSQL)** — the backstop for anything that must hold true no
  matter which code path writes it: `NOT NULL`, foreign keys with the right `ON DELETE` behavior,
  a `CHECK` constraint on `status` and `category` enums, a `UNIQUE` constraint on
  `(report_id, approver_id)` in the approver-assignment table so the same approver can't be
  double-assigned. Business *rules* (self-approval, transition legality) are deliberately kept out
  of the database and live in Python, where they can return a specific, explanatory error message
  — Postgres constraints are for invariants that should never be violated regardless of which
  application code runs, not for rules that need to produce a human-readable "why."

## Report lifecycle

States: `draft → submitted → approved | rejected`, `approved → paid`, `rejected → draft`.

Enforced through one central function, not scattered per-route checks:

```
can_transition(report, action, actor) -> (allowed: bool, reason: str | None)
```

This single function is called by every endpoint that changes status — `submit`, `approve`,
`reject`, `mark_paid` — and by the bulk-approve/bulk-reject endpoints (looped per report, per
goal 7's explicit requirement that bulk actions check each report individually). Centralizing it
means the self-approval rule, the "only Submitted can be approved/rejected" rule, and the
"reject requires a reason" rule are each written exactly once and can't drift between the
single-report and bulk code paths.

A transition that isn't allowed returns a 4xx response with the `reason` string from
`can_transition`, satisfying the README's "any other transition must be rejected... with a
message explaining why" — not a bare status code.

A successful transition is written inside a single database transaction together with its
history record (see below), so a status change and its audit trail can never diverge.

## Immutable history

Every status change and every comment is an append-only row, never updated or deleted:

- `report_events` — one row per transition: `report_id`, `actor_id`, `from_status`, `to_status`,
  `reason` (nullable, populated on reject), `created_at`.
- `report_comments` — one row per comment: `report_id`, `author_id`, `body`, `created_at`.

Two layers of enforcement, matching the Validation split above:

- **Application layer** — there is no `PATCH`/`DELETE` route for either table. The capability to
  edit or remove a history entry simply doesn't exist in the API surface.
- **Database layer** — a `BEFORE UPDATE OR DELETE` trigger on `report_events` and
  `report_comments` raises an exception, so even a bug in application code (a stray query, a
  future refactor that adds an edit route by mistake) cannot silently violate "nothing in this
  timeline can be edited or deleted after the fact, including by approvers." This is the one
  place a DB-level guarantee is used instead of relying on application discipline alone, because
  the README calls out immutability as a hard requirement rather than a UI nicety.

  This was originally designed as revoked `UPDATE`/`DELETE` grants and changed during
  implementation — a revoke does not bind the table's owner, which is exactly the role a
  single-role free-tier deployment connects as. See `docs/decisions.md`, Decision 5.

Every lifecycle transition writes its `report_events` row in the same transaction as the status
update (see the end-to-end walkthrough below), so a report's current `status` and its timeline
are always consistent — there is no code path that changes one without the other.

## Approver assignment

`report_approvers` is a many-to-many join table (`report_id`, `approver_id`, `assigned_at`,
unique on the pair) between `expense_reports` and `users`.

Two read views for approvers, both server-side queries, not client-side filtering of one big
list:

- **Full queue** — every `submitted` report, regardless of assignment.
- **Assigned to me** — every `submitted` report where a `report_approvers` row exists for the
  current approver.

Assignment is a **routing/visibility mechanism**, not an additional authorization gate: per the
README, the ability to approve/reject a submitted report is governed by role + non-ownership
only (goal 4), not by whether that approver happens to be assigned. This is a genuine ambiguity
in the brief worth stating plainly here: an assigned approver's "queue" is a convenience filter,
while decision authority is uniformly "any approver, on any report they don't own." This
interpretation is recorded as a decision in `docs/decisions.md` rather than left implicit.

## Dashboard

A read-only aggregation layer — no new writable state, just server-side `SUM`/`COUNT`/
`GROUP BY` queries, scoped by the same role/ownership rules as everything else (an employee's
dashboard reflects their own reports; an approver's reflects everything they can see):

- Headline counts: reports awaiting approval, total due (`SUM(total)` where `status = approved`),
  approved-this-week count, paid-this-week count.
- Status breakdown: `GROUP BY status`.
- Category breakdown: `GROUP BY category` over expense lines (chosen over grouping by report,
  since a report can span multiple categories — recorded as a decision).
- Weekly paid total, last 8 weeks: one query bucketing `paid_at` by week, with weeks that have
  zero paid reports still present as `0` in the series (generated via a date-series join, not
  simply omitted, so the chart isn't misleading).

All four are separate, focused queries rather than one large denormalized read model — at this
data scale there's no performance reason to pre-aggregate, and keeping them as plain queries
keeps `docs/schema.md`'s "what breaks at 100x data" question honest (the answer being: these
queries, first, and that's where a materialized/cached rollup would go).

## Search/filter/sort/pagination

One endpoint, `GET /reports`, all four concerns handled inside the same SQL query:

- **Search** — `ILIKE '%term%'` on `title` (acceptable at this scale; a `tsvector`/GIN index is
  the documented upgrade path if the dataset grew, noted in `schema.md`, not built now).
- **Filter** — optional `status`, `owner_id`, `approver_id` params, each adding a `WHERE`/`JOIN`
  clause only when present.
- **Sort** — an allow-listed `sort` param mapped to `submitted_at`, `status`, or `total`
  (allow-listed specifically so the param can't be used to inject an arbitrary column/expression).
- **Pagination** — `LIMIT`/`OFFSET` plus a total-match count, either via a second `COUNT(*)`
  query with the same `WHERE` clauses or a `COUNT(*) OVER()` window column on the same query —
  decided during implementation based on which reads more clearly in SQLAlchemy.

The role/ownership scope from Authorization is always applied first, as a base `WHERE` clause
the user-supplied filters are layered on top of — a filter parameter can narrow what's visible,
never widen it (an employee passing `owner_id=<someone else>` has that parameter ignored, not
honored).

## Bulk operations

`POST /reports/bulk-approve` and `POST /reports/bulk-reject` each take a list of report ids
(plus a `reason` for bulk-reject) and loop over them **individually**, calling the same
`can_transition` used by the single-report endpoints. This is not an all-or-nothing transaction —
each report either transitions and gets its own `report_events` row, or is refused with a
specific reason, and the response lists every id's outcome:

```json
{
  "results": [
    { "report_id": 12, "status": "approved" },
    { "report_id": 14, "status": "refused", "reason": "owner_is_approver" },
    { "report_id": 19, "status": "refused", "reason": "not_submitted" }
  ]
}
```

The `"owner_is_approver"` reason is surfaced distinctly from other refusals, per the README's
explicit requirement to name reports rejected specifically because the approver owns them,
separately from any other successes or refusals.

## CSV export

`GET /reports/export/unpaid.csv` runs the same query as "approved, not yet paid" (the source of
the dashboard's "total due" figure — deliberately the same query in both places, not two
independent computations that could drift) and streams it as `text/csv` using Python's stdlib
`csv` module into a `StreamingResponse`. No new dependency, no client-side CSV assembly (the
browser never has the full unpaid list in memory to build a file from — it just downloads what
the server streamed).

## Stale alerts

Computed live from existing data, not a background job and not a stored boolean:

- A report is stale if `status = 'submitted' AND submitted_at < now() - interval 'N days'`.
- A `stale_alert_dismissals` table (`report_id`, `approver_id`, `dismissed_at`) records
  dismissals per assigned approver, not globally — one approver dismissing an alert doesn't hide
  it from a different approver assigned to the same report.
- The alert is suppressed only while `dismissed_at > now() - interval 'M days'`; once that window
  passes, the alert reappears automatically because the query re-evaluates it on every read —
  there's no separate process that has to "remember" to bring it back.
- `GET /alerts/stale` returns the list (and its count, for the nav badge) scoped to the current
  approver's assignments; `POST /reports/{id}/alerts/dismiss` requires the caller to be an
  approver assigned to that report.

`N` and `M` are named constants in one config location, not inline magic numbers, since they're
each referenced from at least two places (the query and, for `M`, the reappearance check within
the same query).

## Optional: LangChain-assisted rejection summary (stretch, not required)

Out of scope for the 10 required goals and only attempted after all ten are solid, per the
README's stretch-idea policy. Documented here for completeness of the architecture, not as a
commitment.

**Idea**: when an approver rejects a report, offer an optional "suggest a reason" action that
sends the report's line items (dates, amounts, categories, descriptions) to an LLM via a small
LangChain chain and returns a drafted rejection reason the approver can edit or discard before
submitting — the approver always makes the final call and the actual submitted `reason` string
still goes through the same required-non-empty validation as any manually typed reason.

**Design constraints if built:**
- Strictly additive and optional — the reject endpoint's contract (reason required, immutable
  history entry) doesn't change; this only pre-fills a text box.
- Isolated in its own module (`ai/` on the backend) behind a single function call, so it can be
  deleted or feature-flagged off with zero impact on the ten required goals if time runs out.
  LangChain's role here is intentionally thin — one prompt template and one LLM call, not an
  agent with tools or a retrieval pipeline, since anything more elaborate is scope this project
  doesn't need.
- Never fed information the requesting approver isn't already authorized to see (it only ever
  operates on a single report the approver is already permitted to view/decide on).
- Requires an API key for whichever LLM provider is used, held as an environment variable like
  every other secret, never in the repository.
- If not built, this section stands as the design for it and nothing else in the system depends
  on it.

## Representative request end-to-end: employee submits an expense report

```
1. Frontend request
   React app: employee clicks "Submit" on their own Draft report.
   → POST /reports/{id}/submit, Authorization: Bearer <JWT>, empty body.

2. Authentication (FastAPI dependency: get_current_user)
   JWT signature and expiry verified. Token's `sub` resolved to a User row.
   Invalid/expired/missing token → 401, request goes no further.

3. Authorization
   Load the report by id. Check current_user.id == report.owner_id.
   (Submit is owner-only — no role check needed beyond "is authenticated,"
   since any authenticated user may submit their own report.)
   Not the owner → 403 with an explanatory message, request goes no further.

4. Validation
   can_transition(report, action="submit", actor=current_user) is called.
   Checks: report.status == "draft" (only Draft reports can be submitted).
   Optionally: report has at least one expense line (decision recorded in
   docs/decisions.md).
   Fails either check → 400 with the specific reason string, no DB write occurs.

5. Database transaction
   Inside one transaction:
     a. UPDATE expense_reports SET status = 'submitted', submitted_at = now()
        WHERE id = :id;
     b. INSERT INTO report_events (report_id, actor_id, from_status, to_status,
        created_at) VALUES (:id, :actor_id, 'draft', 'submitted', now());
   Both statements commit together or neither does — the report can never end
   up Submitted without a matching history row, or vice versa.

6. History record
   Step 5b *is* the history record — written as part of the same transaction,
   not a separate follow-up call, so there's no window where the status has
   changed but the timeline hasn't caught up.

7. Response
   FastAPI serializes the updated report (id, status, submitted_at, total,
   line items) back as JSON. React updates local UI state from this response
   — it does not optimistically assume success before the server confirms it.
```

Every other state-changing action in the system (approve, reject, mark-paid, bulk actions,
comments) follows this same seven-step shape: authenticate → authorize → validate/transition →
transactional write with its history row → response. This request is representative precisely
because it's the simplest instance of that shape — the more complex actions (bulk, reject) are
this same skeleton with more validation branches and, for bulk, a loop around steps 3–6 per
report id.

## What we deliberately will NOT build

- **No microservices.** One FastAPI process, one database. The 10 goals don't need independent
  scaling or deployment of separate services, and splitting them would only add
  network-boundary complexity (service discovery, inter-service auth) with no corresponding
  benefit at this scale.
- **No background job scheduler / cron / task queue.** Stale-alert status is computed live on
  read, not by a periodic job that flags reports — simpler, and can't silently fall behind if a
  scheduled run is missed.
- **No caching layer (Redis, etc.).** Dashboard and search queries run directly against
  Postgres. At demo-data scale this is fast enough, and adding a cache before there's a measured
  reason to is complexity the project doesn't need — noted instead as the documented answer to
  "what would break first at 100x the data" in `schema.md`.
- **No refresh-token rotation, password reset, or email verification.** Out of scope for the
  README's actual asks; a straightforward login + a fixed-expiry JWT is enough for a demo system
  with seeded credentials.
- **No general-purpose RBAC/permissions framework.** Two roles and a small, fixed set of rules
  (role check + ownership check) don't warrant a policy engine — that's solving a more general
  problem than the one in front of us.
- **No event-sourcing / full audit-log framework.** The immutability requirement (goal 9) is
  satisfied by two focused append-only tables guarded by database triggers, not by
  rearchitecting persistence around events.
- **No client-side state management library (Redux/Zustand/etc.), no client-side data cache
  (React Query, etc.).** A handful of screens with plain component state and direct API calls is
  enough; the server is the single source of truth for everything the UI shows, so there's
  little for a client cache to buy beyond avoiding a redundant request or two.
- **No design system / component library setup.** Plain CSS or a minimal utility framework —
  this is an internal tool with roughly five screens, not a product needing a visual system.
- **The full stretch-ideas list from the README** (OCR receipts, mileage calculator,
  multi-currency, multi-level approval chains, per-category policy limits, corporate-card
  reconciliation, mobile capture, recurring templates, budget-vs-actual reporting) — explicitly
  optional, and none attempted unless all 10 required goals are solidly done first with time
  remaining. The one stretch idea given any design treatment here (LangChain rejection-reason
  suggestions) is scoped deliberately small for exactly that reason.
