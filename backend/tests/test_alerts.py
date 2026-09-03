"""Stale-approval alerts (goal 10).

The rule that a boolean flag could not express: a dismissed alert comes *back* if the
report is still undecided a set number of days later. These tests move the clock by
editing timestamps rather than waiting, then assert the alert reappears on its own.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.models import ExpenseReport, StaleAlertDismissal
from app.models.enums import UserRole


def _age_submission(db, report_id: int, days: int) -> None:
    """Backdate a report's submission so it is `days` old."""
    report = db.get(ExpenseReport, report_id)
    report.submitted_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.commit()


def _submitted_and_assigned(client, auth, make_report, db, owner, approver, days_old):
    report = make_report(owner, title=f"Waiting {days_old} days")
    client.post(
        f"/reports/{report['id']}/approvers",
        json={"approver_id": approver.id},
        headers=auth(owner),
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(owner))
    _age_submission(db, report["id"], days_old)
    return report


def test_a_report_becomes_stale_only_after_the_threshold(
    client, auth, make_report, db, employee, approver
):
    fresh = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days - 1
    )
    stale = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )

    alerts = client.get("/alerts/stale", headers=auth(approver)).json()

    ids = [item["report"]["id"] for item in alerts["items"]]
    assert stale["id"] in ids
    assert fresh["id"] not in ids
    assert alerts["count"] == 1  # this count drives the nav badge


def test_dismissing_hides_the_alert_then_it_returns(
    client, auth, make_report, db, employee, approver
):
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )

    def alert_count() -> int:
        return client.get("/alerts/stale", headers=auth(approver)).json()["count"]

    assert alert_count() == 1

    dismissed = client.post(
        f"/reports/{report['id']}/alerts/dismiss", headers=auth(approver)
    )
    assert dismissed.status_code == 204
    assert alert_count() == 0

    # Move the dismissal past the re-alert window: the alert comes back by itself,
    # with no job having run.
    record = db.scalar(
        select(StaleAlertDismissal).where(StaleAlertDismissal.report_id == report["id"])
    )
    record.dismissed_at = datetime.now(timezone.utc) - timedelta(
        days=settings.stale_realert_after_days + 1
    )
    db.commit()

    assert alert_count() == 1


def test_a_dismissal_only_hides_the_alert_for_that_approver(
    client, auth, make_report, db, employee, approver, make_user
):
    other_approver = make_user(UserRole.approver, "Approver Two")
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )
    client.post(
        f"/reports/{report['id']}/approvers",
        json={"approver_id": other_approver.id},
        headers=auth(employee),
    )

    client.post(f"/reports/{report['id']}/alerts/dismiss", headers=auth(approver))

    assert client.get("/alerts/stale", headers=auth(approver)).json()["count"] == 0
    assert client.get("/alerts/stale", headers=auth(other_approver)).json()["count"] == 1


def test_only_an_assigned_approver_may_dismiss(
    client, auth, make_report, db, employee, approver, make_user
):
    unassigned_approver = make_user(UserRole.approver, "Approver Two")
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )

    refused = client.post(
        f"/reports/{report['id']}/alerts/dismiss", headers=auth(unassigned_approver)
    )
    by_owner = client.post(
        f"/reports/{report['id']}/alerts/dismiss", headers=auth(employee)
    )

    assert refused.status_code == 403
    assert by_owner.status_code == 403


def test_deciding_a_report_clears_its_alert_immediately(
    client, auth, make_report, db, employee, approver
):
    """Staleness is recomputed on read, so a decision ends the alert at once."""
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 5
    )
    assert client.get("/alerts/stale", headers=auth(approver)).json()["count"] == 1

    client.post(f"/reports/{report['id']}/approve", headers=auth(approver))

    assert client.get("/alerts/stale", headers=auth(approver)).json()["count"] == 0


def test_resubmitting_starts_a_fresh_alert_clock(
    client, auth, make_report, db, employee, approver
):
    """An old dismissal must not suppress the alert for a *new* submission."""
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )
    client.post(f"/reports/{report['id']}/alerts/dismiss", headers=auth(approver))
    assert client.get("/alerts/stale", headers=auth(approver)).json()["count"] == 0

    client.post(
        f"/reports/{report['id']}/reject", json={"reason": "Redo"}, headers=auth(approver)
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    _age_submission(db, report["id"], settings.stale_after_days + 1)

    assert client.get("/alerts/stale", headers=auth(approver)).json()["count"] == 1


def test_employees_see_their_own_stale_reports_but_cannot_dismiss(
    client, auth, make_report, db, employee, approver
):
    report = _submitted_and_assigned(
        client, auth, make_report, db, employee, approver, settings.stale_after_days + 1
    )

    alerts = client.get("/alerts/stale", headers=auth(employee)).json()

    assert alerts["count"] == 1
    assert alerts["items"][0]["report"]["id"] == report["id"]
    assert alerts["items"][0]["can_dismiss"] is False
