"""The report lifecycle: Draft → Submitted → Approved/Rejected, Approved → Paid.

Every rule about who may change a report's status lives in `can_transition`, and every
path that changes status goes through `apply_transition`. That is deliberate: the brief
states the self-approval rule four separate times (approve, reject, mark-paid, and inside
bulk actions), and four implementations of one rule is four chances for them to disagree.
Because the bulk endpoints call the same function per report, a bulk refusal and a
single-report refusal are provably the same decision.

Rejection is handled literally as the brief describes it — "the report then returns to
Draft, where its owner can edit it and submit it again". So a rejection writes *two*
history rows in one transaction (submitted→rejected carrying the reason, then
rejected→draft) and leaves the report in Draft. The rejection and its reason stay
permanently visible in the timeline; the report is immediately editable again.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ExpenseLine, ExpenseReport, ReportEvent, StaleAlertDismissal, User
from app.models.enums import ReportStatus


class Action(str, Enum):
    submit = "submit"
    approve = "approve"
    reject = "reject"
    mark_paid = "mark_paid"


class Refusal(str, Enum):
    """Machine-readable refusal codes.

    `owner_is_approver` exists as its own code because goal 7 requires bulk results to
    name the reports refused *specifically* because the approver owned them, separately
    from every other kind of refusal.
    """

    not_owner = "not_owner"
    owner_is_approver = "owner_is_approver"
    not_approver_role = "not_approver_role"
    wrong_status = "wrong_status"
    no_lines = "no_lines"
    missing_reason = "missing_reason"


@dataclass(frozen=True)
class TransitionOutcome:
    allowed: bool
    target_status: ReportStatus | None = None
    code: Refusal | None = None
    message: str | None = None


def _refuse(code: Refusal, message: str) -> TransitionOutcome:
    return TransitionOutcome(allowed=False, code=code, message=message)


def _require_decider(report: ExpenseReport, actor: User) -> TransitionOutcome | None:
    """Shared gate for approve/reject/mark-paid: approver role, and not the owner.

    Ownership is checked before status on purpose. A report that is both owned by the
    actor and in the wrong status is reported as `owner_is_approver`, because that is the
    refusal the brief asks to be surfaced distinctly.
    """
    if not actor.is_approver:
        return _refuse(
            Refusal.not_approver_role,
            "Deciding on a report requires the approver role.",
        )
    if actor.id == report.owner_id:
        return _refuse(
            Refusal.owner_is_approver,
            "You cannot decide on your own report, even though you hold the approver "
            "role. It must wait for a different approver.",
        )
    return None


def can_transition(
    *,
    report: ExpenseReport,
    action: Action,
    actor: User,
    line_count: int | None = None,
    reason: str | None = None,
) -> TransitionOutcome:
    """Decide whether `actor` may apply `action` to `report`, and say why not if refused."""

    if action is Action.submit:
        if actor.id != report.owner_id:
            return _refuse(
                Refusal.not_owner, "Only the report's owner can submit it for approval."
            )
        if report.status is not ReportStatus.draft:
            return _refuse(
                Refusal.wrong_status,
                f"Only a Draft report can be submitted; this report is {report.status.value}.",
            )
        if not line_count:
            return _refuse(
                Refusal.no_lines,
                "A report needs at least one expense line before it can be submitted.",
            )
        return TransitionOutcome(allowed=True, target_status=ReportStatus.submitted)

    if action is Action.approve:
        refusal = _require_decider(report, actor)
        if refusal:
            return refusal
        if report.status is not ReportStatus.submitted:
            return _refuse(
                Refusal.wrong_status,
                f"Only a Submitted report can be approved; this report is "
                f"{report.status.value}.",
            )
        return TransitionOutcome(allowed=True, target_status=ReportStatus.approved)

    if action is Action.reject:
        refusal = _require_decider(report, actor)
        if refusal:
            return refusal
        if report.status is not ReportStatus.submitted:
            return _refuse(
                Refusal.wrong_status,
                f"Only a Submitted report can be rejected; this report is "
                f"{report.status.value}.",
            )
        if reason is None or not reason.strip():
            return _refuse(
                Refusal.missing_reason, "Rejecting a report requires a reason."
            )
        return TransitionOutcome(allowed=True, target_status=ReportStatus.rejected)

    if action is Action.mark_paid:
        refusal = _require_decider(report, actor)
        if refusal:
            return refusal
        if report.status is not ReportStatus.approved:
            return _refuse(
                Refusal.wrong_status,
                f"Only an Approved report can be marked Paid; this report is "
                f"{report.status.value}.",
            )
        return TransitionOutcome(allowed=True, target_status=ReportStatus.paid)

    raise ValueError(f"Unknown action: {action}")  # pragma: no cover - guarded by enum


def line_count_for(db: Session, report_id: int) -> int:
    return (
        db.scalar(select(func.count(ExpenseLine.id)).where(ExpenseLine.report_id == report_id))
        or 0
    )


def apply_transition(
    db: Session,
    *,
    report: ExpenseReport,
    action: Action,
    actor: User,
    reason: str | None = None,
    at: datetime | None = None,
) -> TransitionOutcome:
    """Validate and perform a transition, writing its history in the same transaction.

    Does not commit — the caller controls the transaction boundary, which is what lets a
    bulk action commit a whole batch of independently-decided reports at once.

    `at` overrides the timestamp. Only the seed script passes it, so demo data can have a
    realistic history spread over past weeks; because history rows are immutable once
    written, backdating has to happen at insert time rather than by a later UPDATE.
    """
    outcome = can_transition(
        report=report,
        action=action,
        actor=actor,
        line_count=line_count_for(db, report.id) if action is Action.submit else None,
        reason=reason,
    )
    if not outcome.allowed:
        return outcome

    now = at or datetime.now(timezone.utc)
    previous = report.status

    if action is Action.submit:
        report.status = ReportStatus.submitted
        report.submitted_at = now
        # A fresh submission starts a clean alert slate: a dismissal from a previous
        # round must not suppress an alert about this one.
        db.execute(
            delete(StaleAlertDismissal).where(StaleAlertDismissal.report_id == report.id)
        )
        _record(db, report, actor, previous, ReportStatus.submitted, None, now)

    elif action is Action.approve:
        report.status = ReportStatus.approved
        report.decided_at = now
        _record(db, report, actor, previous, ReportStatus.approved, None, now)

    elif action is Action.reject:
        report.decided_at = now
        # Two rows: the rejection (with its reason) is permanent history, and the report
        # then returns to Draft so its owner can fix and resubmit it.
        _record(db, report, actor, previous, ReportStatus.rejected, reason, now)
        _record(db, report, actor, ReportStatus.rejected, ReportStatus.draft, None, now)
        report.status = ReportStatus.draft
        report.submitted_at = None  # it is no longer awaiting a decision

    elif action is Action.mark_paid:
        report.status = ReportStatus.paid
        report.paid_at = now
        _record(db, report, actor, previous, ReportStatus.paid, None, now)

    return outcome


def _record(
    db: Session,
    report: ExpenseReport,
    actor: User,
    from_status: ReportStatus,
    to_status: ReportStatus,
    reason: str | None,
    at: datetime,
) -> None:
    db.add(
        ReportEvent(
            report_id=report.id,
            actor_id=actor.id,
            from_status=from_status,
            to_status=to_status,
            reason=reason.strip() if reason else None,
            created_at=at,
        )
    )
