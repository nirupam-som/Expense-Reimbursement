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

*To be filled in per session as the work happens.*

## What was cut when time ran short

*To be filled in.*
