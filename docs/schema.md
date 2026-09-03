# Schema

Proposed PostgreSQL schema for all 10 required goals. This is a design proposal, not yet
implemented — no migrations exist yet. Written against the design in `docs/architecture.md`.

## Entity overview

| Table | Purpose | Relationship shape |
|---|---|---|
| `users` | Accounts, one row per person, holds role | referenced by almost everything |
| `expense_reports` | One report per (owner, trip/period) | many-to-one → `users` (owner) |
| `expense_lines` | Line items on a report | many-to-one → `expense_reports` |
| `report_approvers` | Who may be routed a report | many-to-many, `users` ↔ `expense_reports` |
| `report_events` | Immutable status-change history | many-to-one → `expense_reports`, → `users` (actor) |
| `report_comments` | Immutable comment thread | many-to-one → `expense_reports`, → `users` (author) |
| `stale_alert_dismissals` | Per-approver dismissal state | many-to-many-ish, `users` ↔ `expense_reports` |

Two Postgres `ENUM` types are used across tables rather than free-text columns, so illegal values
are rejected at the database layer regardless of which application code writes them:

- `user_role`: `employee`, `approver`
- `report_status`: `draft`, `submitted`, `approved`, `rejected`, `paid`
- `expense_category`: `travel`, `lodging`, `meals`, `transportation`, `supplies`, `other`
  (placeholder list — the exact category set is a business decision, not an architectural one;
  easy to extend by adding an enum value via migration).

## `users`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL | PK | |
| `email` | `CITEXT` | NOT NULL | UNIQUE | case-insensitive so `A@x.com`/`a@x.com` can't both register |
| `password_hash` | `TEXT` | NOT NULL | | bcrypt hash, never the plaintext |
| `role` | `user_role` | NOT NULL | | `employee` or `approver` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |

**Indexes**: unique index on `email` (from the `UNIQUE` constraint — this is also the login
lookup path, so it's load-bearing, not incidental).

**Deliberately omitted**: no `updated_at`, no soft-delete flag, no profile fields. Nothing in the
10 goals requires editing a user record after creation or deactivating one.

## `expense_reports`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL | PK | |
| `owner_id` | `BIGINT` | NOT NULL | FK → `users(id)` ON DELETE RESTRICT | |
| `title` | `TEXT` | NOT NULL | | |
| `date_range_start` | `DATE` | NOT NULL | | |
| `date_range_end` | `DATE` | NOT NULL | | CHECK `date_range_end >= date_range_start` |
| `status` | `report_status` | NOT NULL DEFAULT `'draft'` | | |
| `is_archived` | `BOOLEAN` | NOT NULL DEFAULT `false` | | |
| `submitted_at` | `TIMESTAMPTZ` | NULL | | set once, on submit |
| `decided_at` | `TIMESTAMPTZ` | NULL | | set on approve/reject |
| `paid_at` | `TIMESTAMPTZ` | NULL | | set on mark-paid |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | bumped on any field change |

**Foreign keys**: `owner_id → users(id)`, `ON DELETE RESTRICT` — a user with any reports can't be
hard-deleted, which is fine since the app never deletes users anyway; it's a safety rail against
an accidental future delete path, not a feature.

**Indexes**:
- `owner_id` — every employee-scoped query filters on this.
- `status` — every queue/filter query filters on this.
- composite `(status, submitted_at)` — serves the stale-alert query (`status = 'submitted' AND
  submitted_at < ...`) and the "sort by submitted date" case together.
- `is_archived` — default-view queries always exclude archived reports; a **partial** index
  (`CREATE INDEX ... ON expense_reports (owner_id) WHERE is_archived = false`) is the natural
  upgrade if this table gets large, since almost every query filters out archived rows first —
  noted as the upgrade path, not built now.

**Not indexed (yet)**: `title`. Search uses `ILIKE '%term%'`, which a plain B-tree index can't
serve (leading wildcard). A `pg_trgm` GIN index is the documented upgrade path — see "what
breaks first at 100x" below.

**No `total_amount` column.** This is the one genuinely debated design choice on this table —
see "How totals are calculated," below.

## `expense_lines`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL | PK | |
| `report_id` | `BIGINT` | NOT NULL | FK → `expense_reports(id)` ON DELETE CASCADE | |
| `date` | `DATE` | NOT NULL | | |
| `amount` | `NUMERIC(12,2)` | NOT NULL | | CHECK `amount > 0` |
| `category` | `expense_category` | NOT NULL | | |
| `description` | `TEXT` | NOT NULL | | CHECK `length(trim(description)) > 0` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |

**Foreign keys**: `report_id → expense_reports(id)`, `ON DELETE CASCADE` — lines have no
existence independent of their report; if a report row is ever removed, its lines should go with
it. (In practice reports are archived, never hard-deleted, so this cascade is a safety property,
not something exercised in normal operation.)

**Indexes**: `report_id` (fetch-all-lines-for-a-report is the single most common line query, and
also feeds the total-amount aggregate and the dashboard's category breakdown). A composite
`(report_id, category)` is worth adding once the category breakdown query is written, to let
Postgres satisfy the `GROUP BY category` without a separate scan — noted as a likely addition
once real query plans are checked, not assumed necessary upfront.

**Money type**: `NUMERIC(12,2)`, not `FLOAT`/`DOUBLE PRECISION` — floating point cannot represent
currency exactly and must never be used for a sum that has to reconcile to the cent.

**Mutability**: lines may only be added/edited/deleted while their parent report's `status =
'draft'`. This is **not** a database constraint (see below) — it's checked in the application
before every write, because it depends on the *current* value of a different table's row and on
comparing that live, not on a static property of the line row itself.

## `report_approvers` (many-to-many)

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `report_id` | `BIGINT` | NOT NULL | PK (composite), FK → `expense_reports(id)` ON DELETE CASCADE | |
| `approver_id` | `BIGINT` | NOT NULL | PK (composite), FK → `users(id)` ON DELETE CASCADE | |
| `assigned_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |

Composite primary key `(report_id, approver_id)` — this table has no identity of its own beyond
the pair, so a surrogate `id` column would be pure overhead. The composite PK also *is* the
uniqueness constraint: the same approver can't be assigned to the same report twice, enforced by
the database, not by an application "check before insert."

**Indexes**: the PK covers `report_id`-first lookups (all approvers for a report). A secondary
index on `approver_id` alone is needed for the reverse direction — "all reports assigned to this
approver," i.e. the "assigned to me" queue.

**Deliberately not enforced here**: that `approver_id != expense_reports.owner_id`. A `CHECK`
constraint can't reference another table, and a cross-table trigger would duplicate a rule that
already has a single home — the `can_transition` check applied at decision time (approve/reject/
mark-paid). An approver being assigned to their own report is harmless by itself; they still
can't act on it. Enforcing it at assignment time too would be a second copy of the same rule with
no functional benefit — see "How self-approval is prevented" below.

## `report_events` (immutable status history)

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL | PK | |
| `report_id` | `BIGINT` | NOT NULL | FK → `expense_reports(id)` ON DELETE CASCADE | |
| `actor_id` | `BIGINT` | NOT NULL | FK → `users(id)` ON DELETE RESTRICT | |
| `from_status` | `report_status` | NOT NULL | | every row is a real transition, never the initial Draft |
| `to_status` | `report_status` | NOT NULL | | |
| `reason` | `TEXT` | NULL | | populated only when `to_status = 'rejected'` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |

**Indexes**: `(report_id, created_at)` — a report's timeline is always fetched as "all events for
this report, in order."

**Why `actor_id` is `ON DELETE RESTRICT` rather than `CASCADE`**: history must keep saying *who*
made a change even in a hypothetical future where users can be removed. Cascading the delete
would silently destroy audit history; restricting it forces a real decision (e.g., anonymize
instead of delete) if that need ever arises. Not a feature being built now — just the safer
default given the immutability requirement.

## `report_comments` (immutable)

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL | PK | |
| `report_id` | `BIGINT` | NOT NULL | FK → `expense_reports(id)` ON DELETE CASCADE | |
| `author_id` | `BIGINT` | NOT NULL | FK → `users(id)` ON DELETE RESTRICT | |
| `body` | `TEXT` | NOT NULL | | CHECK `length(trim(body)) > 0` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | |

**Indexes**: `(report_id, created_at)`, same reasoning as `report_events` — and in the UI these
two tables are likely merged into a single chronological timeline, which is a read-time `UNION`/
interleave, not a reason to merge them at the storage layer (they have different shapes: events
always have a status transition, comments never do).

**Who may comment**: the report's owner, or any approver (any approver, not only ones assigned to
that report — consistent with the same "approvers can act on any report they don't own" reading
used for decisions, recorded in `docs/architecture.md`). Enforced in application code at write
time, not by a DB constraint, since it depends on the caller's identity and role, not on a static
property of the row.

## `stale_alert_dismissals`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `report_id` | `BIGINT` | NOT NULL | PK (composite), FK → `expense_reports(id)` ON DELETE CASCADE | |
| `approver_id` | `BIGINT` | NOT NULL | PK (composite), FK → `users(id)` ON DELETE CASCADE | |
| `dismissed_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | | overwritten on re-dismiss |

Composite PK again, for the same reason as `report_approvers` — the pair is the identity. Unlike
`report_events`/`report_comments`, this table is **intentionally mutable**: dismissing an
already-dismissed, since-reappeared alert is an `UPSERT`
(`INSERT ... ON CONFLICT (report_id, approver_id) DO UPDATE SET dismissed_at = now()`), not a new
row. Goal 9's immutability requirement is scoped to the report's status/comment history — nothing
in the README asks for a permanent audit trail of every dismiss/reappear cycle, so this table
doesn't carry that constraint.

**Indexes**: PK covers `report_id`-first lookups; `approver_id` alone is needed for "all of this
approver's dismissals," used when computing their personalized alert list.

## One-to-many relationships

- `users` → `expense_reports` (`owner_id`): one owner, many reports.
- `expense_reports` → `expense_lines` (`report_id`): one report, many lines.
- `expense_reports` → `report_events` (`report_id`): one report, many history entries.
- `expense_reports` → `report_comments` (`report_id`): one report, many comments.
- `users` → `report_events` (`actor_id`): one user can be the actor on many events, across many
  reports.
- `users` → `report_comments` (`author_id`): one user can author many comments.

## Many-to-many relationships

- `users` (approvers) ↔ `expense_reports`, via `report_approvers`: any number of approvers per
  report, any number of reports per approver.
- `users` (approvers) ↔ `expense_reports`, via `stale_alert_dismissals`: conceptually similar
  shape (a join table keyed by the same pair), but representing per-approver dismissal *state*
  for an alert, not a structural relationship — included here for completeness since it is a
  `users`↔`expense_reports` join table, even though its purpose differs from `report_approvers`.

There is deliberately no many-to-many between `expense_reports` and `expense_lines`, or between
`users` and `expense_lines` — both are strictly one-to-many, owned entirely by their parent
report.

## Database constraints vs. application constraints

The dividing line: **the database enforces invariants that must hold no matter which code path
writes the row; the application enforces rules that depend on who is asking, or on the current
state of a different row.**

**Enforced by PostgreSQL:**
- `NOT NULL` on every required field.
- Foreign keys, with `CASCADE`/`RESTRICT` chosen per relationship as above.
- `UNIQUE` — `users.email`, and the composite primary keys on `report_approvers` and
  `stale_alert_dismissals` (which double as their uniqueness guarantee).
- `CHECK` — `expense_lines.amount > 0`, `expense_reports.date_range_end >= date_range_start`,
  non-empty `description`/`body` text.
- `ENUM` types for `role`, `status`, `category` — an invalid value is rejected at insert/update
  time regardless of which application code, migration, or manual `psql` session wrote it.
- Immutability of `report_events` and `report_comments` — the application's runtime database role
  is granted `INSERT`/`SELECT` only on these two tables, not `UPDATE`/`DELETE`. This is a genuine
  database-layer guarantee, not just an omitted API route — *with one caveat*: it only holds if
  migrations run under a separate, more privileged role than the one the running application
  connects with. If the app connected using the same superuser/owner role used for migrations,
  the revoked grants would be meaningless (the owning role bypasses its own grants). This
  two-roles setup is itself a decision worth recording in `docs/decisions.md` once built.

**Enforced by the application:**
- Self-approval prevention (see below) — inherently needs "who is calling this," which has no
  representation in a static row.
- The full lifecycle transition matrix (`can_transition`) — "is `submitted → approved` legal
  right now, for this actor, on this report" combines role, ownership, and current status in one
  decision that produces a specific, human-readable rejection reason, which a `CHECK` constraint
  cannot do (a `CHECK` can only pass/fail, it cannot say *why* in a way the API returns to the
  caller).
- Expense line mutability gated by report status (`draft` only) — depends on a different table's
  current value, not expressible as a constraint local to `expense_lines`.
- Report total calculation — computed, not stored (see below).
- Bulk-action per-report evaluation and the `owner_is_approver` reason categorization.
- Search/filter/sort/pagination query construction, and scoping every query by the caller's
  role/ownership before any user-supplied filter is applied.
- Stale-alert day thresholds (`N`, `M`) — these are configuration values, not schema.

## How immutable history is protected

Two independent layers, deliberately redundant:

1. **No API route exists** to update or delete a `report_events` or `report_comments` row. The
   capability simply isn't wired up in FastAPI.
2. **The database role the application connects as has no `UPDATE`/`DELETE` grant** on either
   table. Even a future bug — a stray migration, a copy-pasted route, a raw query slipped into an
   unrelated handler — cannot mutate history, because the database itself refuses the statement,
   independent of application logic being correct.

Layer 2 is the one that actually matters for the README's "nothing in this timeline can be
edited or deleted after the fact, **including by approvers**" — it holds regardless of role
checks in application code, which is the strongest available guarantee at this stack's
disposal without going as far as event-sourcing or a write-once storage engine (deliberately not
built — see `docs/architecture.md`'s "what we will not build").

## How report totals are calculated from expense lines

**Decision: computed at read time (`SELECT COALESCE(SUM(amount), 0) FROM expense_lines WHERE
report_id = :id`), never stored as a writable column on `expense_reports`.**

Trade-off considered and rejected: a cached `total_amount` column on `expense_reports`, updated
by a trigger (or application code) whenever a line is inserted/updated/deleted.

| | Computed on read (chosen) | Cached column + trigger |
|---|---|---|
| Correctness | Always exactly right — there is no state to drift | Right only if every write path that touches lines also updates the cache; a missed trigger/bug silently produces a wrong total |
| Simplicity | One aggregate query, no trigger to write/maintain/test | Requires a trigger (or equivalent app-level discipline) on three operations (insert/update/delete on lines) |
| Read cost | One extra `SUM` per report shown (or one `JOIN`+`GROUP BY` for a list of reports) | Free — the value is just a column |
| Fits the README's rule | Directly satisfies "calculated by the server, never a value the client can set" — there's no column to accidentally expose as writable | Also satisfiable, but adds a second place the rule could be violated (forgetting to protect the cached column from client writes, on top of forgetting to protect the raw lines) |

At this project's scale (a takehome, seeded demo data, not production traffic), correctness and
simplicity outweigh the read cost, so the total is always computed, never stored. This is exactly
the kind of thing flagged as the first thing to reconsider at materially larger scale — see
"what would break first at 100x the data," below — and is recorded as a decision in
`docs/decisions.md`.

## How archived reports work

`is_archived` is a plain boolean on `expense_reports`, **orthogonal to `status`**. Archiving
never changes `status` and never touches `expense_lines`, `report_events`, or `report_comments` —
it is purely a visibility flag:

- Default list/search queries (Goal 6) add `WHERE is_archived = false` unless the caller
  explicitly asks to include archived reports.
- Archive/restore are two small endpoints that flip the flag and write nothing else — they are
  **not** lifecycle transitions and do **not** produce a `report_events` row, since they aren't a
  status change (a report can be archived from any status — Draft, Approved, Paid, etc. — without
  its underlying status changing).
- A report's detail view, timeline, and comments remain fully intact and reachable by id whether
  archived or not — "removes old reports from the default view without destroying their history"
  is satisfied by never touching history at all, rather than by any special-case restore logic.

## How self-approval is prevented

This rule — an approver can never approve, reject, or mark-paid a report they own, even though
they hold the approver role — **cannot be expressed as a database constraint**, for a structural
reason: a `CHECK` constraint can only see the columns of the row being written; it has no concept
of "who is making this request." `expense_reports.owner_id` and the identity of the person
calling `POST /reports/:id/approve` are two facts that only meet inside the application, at
request time.

So the rule lives in exactly one place — the `can_transition(report, action, actor)` function
described in `docs/architecture.md` — which every route that changes status calls, including
each iteration of the bulk-approve/bulk-reject loop. Concretely, it compares
`actor.id == report.owner_id` and, if true, refuses the transition with a specific reason
(`owner_is_approver`) regardless of `actor.role`. Centralizing it here — rather than checking it
separately in the single-report route and again in the bulk route — is what guarantees the bulk
endpoint's per-report `owner_is_approver` result (Goal 7) and the single-report 403 (Goal 4) can
never disagree, because they're the same function call.

## What would break first at 100x the data

Ranked by how soon each would become a visible problem, assuming the schema above and no other
changes:

1. **Title search (`ILIKE '%term%'`).** A leading wildcard can't use a B-tree index, so this is
   already a full-table scan today — at 100x the rows it becomes the first query anyone notices
   is slow, since it's on the most-used screen (the report list). Fix: a `pg_trgm` GIN index on
   `title` (`CREATE EXTENSION pg_trgm; CREATE INDEX ... USING GIN (title gin_trgm_ops)`), or move
   to Postgres full-text search (`tsvector`) if search needs to expand beyond title.

2. **`OFFSET`-based pagination.** `LIMIT 20 OFFSET 50000` forces Postgres to walk and discard the
   first 50,000 matching rows before returning the page — cost grows linearly with page depth.
   Fine at demo scale (a handful of pages); at 100x data, deep pages on the report list become
   the second-most-visible slowdown. Fix: keyset/cursor pagination (`WHERE (sort_col, id) >
   (:last_sort_col, :last_id) ORDER BY sort_col, id LIMIT 20`).

3. **Live total-amount aggregation across a report list.** Computing `SUM(amount)` per report for
   every row in a paginated list (rather than one grouped join covering the whole page at once)
   turns an N-row page into N+1 queries if implemented naively. Fix, in order of effort: first,
   make sure it's a single `JOIN ... GROUP BY` per page rather than a per-row subquery; only if
   that's still too slow at real scale, revisit the cached-column trade-off documented above.

4. **Dashboard aggregates recomputed on every load.** `SUM`/`COUNT`/`GROUP BY` over the full
   `expense_reports`/`expense_lines` tables is cheap today; at 100x rows, and if the dashboard is
   loaded frequently (e.g., left open, auto-refreshing), this becomes real, repeated load. Fix: a
   materialized view refreshed on a short interval, or an application-level cache with a
   short TTL — deliberately not built now (see `docs/architecture.md`'s "no caching layer"),
   since it's premature at this project's actual scale.

5. **The `report_events`/`report_comments` timeline join for very old, very long-lived reports.**
   Unlikely to matter before the above four, since even a heavily-revised report has a handful to
   a few dozen events/comments, not thousands — included for completeness, not because it's a
   near-term concern.

The common thread: everything on this list is a **read-path** problem (search, pagination,
aggregation), not a write-path or integrity problem — the constraints and relationships in this
schema hold at any scale; what degrades is query performance under naive query patterns, which is
the correct place for that risk to live at this project's size (fix it when a real access pattern
demands it, not preemptively).
