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

*To be filled in as implementation exposes anything the design got wrong.*
