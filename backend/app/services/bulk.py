"""Bulk approve / bulk reject (goal 7).

Not an all-or-nothing transaction: the server checks every report individually, using the
exact same `apply_transition` the single-report endpoints use, and reports the outcome per
report. Reports refused because the approver owns them are counted and coded separately
from every other refusal, which is the specific thing the brief asks for.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExpenseReport, User
from app.services.lifecycle import Action, Refusal, apply_transition


def bulk_decide(
    db: Session,
    *,
    actor: User,
    report_ids: list[int],
    action: Action,
    reason: str | None = None,
) -> dict:
    # Preserve the caller's order, but act on each report once: a repeated id would
    # otherwise "fail" the second time purely because the first attempt succeeded.
    ordered_ids = list(dict.fromkeys(report_ids))

    reports = {
        report.id: report
        for report in db.scalars(
            select(ExpenseReport).where(ExpenseReport.id.in_(ordered_ids))
        ).all()
    }

    success_outcome = "approved" if action is Action.approve else "rejected"
    results: list[dict] = []
    succeeded = refused = owned_by_you = 0

    for report_id in ordered_ids:
        report = reports.get(report_id)

        if report is None:
            refused += 1
            results.append(
                {
                    "report_id": report_id,
                    "outcome": "not_found",
                    "refusal_code": None,
                    "message": "No such report.",
                }
            )
            continue

        outcome = apply_transition(
            db, report=report, action=action, actor=actor, reason=reason
        )

        if outcome.allowed:
            succeeded += 1
            results.append(
                {"report_id": report_id, "outcome": success_outcome, "refusal_code": None,
                 "message": None}
            )
            continue

        refused += 1
        if outcome.code is Refusal.owner_is_approver:
            owned_by_you += 1
        results.append(
            {
                "report_id": report_id,
                "outcome": "refused",
                "refusal_code": outcome.code.value if outcome.code else None,
                "message": outcome.message,
            }
        )

    db.commit()

    return {
        "results": results,
        "succeeded": succeeded,
        "refused": refused,
        "owned_by_you": owned_by_you,
    }
