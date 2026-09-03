# Plan

*Filled in as the work happens, not reconstructed at the end.*

## How the work is split into sessions

Roughly 2 hours per session, six sessions, ordered so the rule-dense core (lifecycle,
self-approval, immutable history) lands early and everything later builds on top of it rather
than retrofitting it.

| # | Session | Planned scope | Estimated | Actual |
|---|---|---|---|---|
| 1 | Foundations | Scaffold, Postgres, migrations, users + auth (JWT), role field, seed script started | 2h | — |
| 2 | Reports & lines (Goals 2, 3) | Report CRUD, line CRUD, Draft-only edit lock, server-computed totals | 2h | — |
| 3 | Lifecycle & approvers (Goals 4, 5) | Central transition function, submit/approve/reject/mark-paid, self-approval block, approver assignment, approver queue | 2h | — |
| 4 | History & alerts (Goals 9, 10) | Immutable `report_events` + comments written transactionally with each transition, timeline view, stale alerts + dismissal + nav badge | 2h | — |
| 5 | Finding & bulk (Goals 6, 7) | Server-side search/filter/sort/pagination, bulk approve/reject with per-report results, CSV export | 2h | — |
| 6 | Dashboard, deploy, docs (Goal 8) | Dashboard aggregates + 8-week chart, deployment, seed demo data, finish docs | 2h | — |

## Why this order

- **Auth first** because every other endpoint's authorization depends on knowing who is calling.
- **Lifecycle before history** would have been wrong — they go in the same session (3 then 4,
  back to back) because every transition must write its history row in the same transaction. Any
  gap between building them invites a code path that changes status without recording it.
- **Search, bulk and dashboard last** because they are all *readers* of a model that has to be
  correct first. Bulk actions in particular reuse the single-report transition function, so they
  cannot be built before it exists.
- **Deployment early enough to not be a surprise**: a hello-world deploy is done in session 1,
  not session 6, so the last session is a redeploy rather than a first attempt.

## Estimated vs. actual

What the estimate got wrong, in both directions:

- **Sessions 3 and 4 were cheaper than budgeted**, because centralising every rule in
  `can_transition()` meant the bulk endpoints (planned for session 5) cost almost nothing when I
  got to them — they are a loop around a function that already existed and was already tested.
  Building the shared function first was the single highest-leverage choice in the project.
- **Session 4 was more expensive than budgeted** in one specific place: the immutability
  guarantee. The design said "revoke UPDATE/DELETE grants", and writing the migration is what
  exposed that a revoke does not bind the table owner — which is the role a single-role free-tier
  deployment uses. Swapping to a trigger and writing a test that proves it with raw SQL took
  longer than the original plan allowed. Recorded as the reversal in `docs/decisions.md`.
- **The test suite cost more than expected**, mostly deliberately: running it against a real
  disposable Postgres built by the actual migrations (rather than SQLite) means it takes ~3
  minutes, but it covers native enums, `NUMERIC` money, `date_trunc` week bucketing and the
  triggers — none of which SQLite would have exercised faithfully.

Two bugs the process caught that the design would not have:

1. `email-validator` rejects reserved TLDs, so the original `@acme.test` demo accounts could
   never have signed in. The seed script wrote them happily (it bypasses Pydantic); the first
   test that tried to *log in* failed immediately.
2. `/health/db` hung for 90 seconds against an unreachable database instead of reporting a
   problem, because the engine had no connect timeout — which would have made the hosting
   platform's readiness probe hang rather than fail.

## What was cut when time ran short

Nothing from the ten goals. What was consciously left out:

- **The optional LangChain rejection-reason assistant.** Designed in `docs/architecture.md`,
  scoped small on purpose, and not built — it is a stretch idea, and stretch ideas do not
  substitute for finishing the ten properly.
- **Frontend tests.** The honest weak point, recorded in `SUBMISSION.md`. With the rules all
  enforced server-side and covered there, UI tests were the least valuable use of the remaining
  time — but "least valuable" is not "worthless", and it is where I would spend the next hour.
- **Inline editing of existing expense lines.** Lines can be added and removed while a report is
  a Draft, but changing one means removing and re-adding it. The API supports `PATCH` on a line;
  the UI does not surface it yet.
- **Every performance improvement `docs/schema.md` identifies** — trigram search index, keyset
  pagination, cached totals, materialised dashboard views. All of them are premature at this
  data scale, and all of them are documented as the upgrade path rather than half-built.
