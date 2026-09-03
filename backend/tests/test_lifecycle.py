"""The report lifecycle and its rules (goal 4).

The transition matrix is table-driven: the brief says any transition other than the legal
ones must be rejected *with a message explaining why*, so every illegal combination is
asserted, not just the interesting ones.
"""

import pytest

from app.models.enums import UserRole


def submit(client, auth, report, user):
    return client.post(f"/reports/{report['id']}/submit", headers=auth(user))


def approve(client, auth, report_id, user):
    return client.post(f"/reports/{report_id}/approve", headers=auth(user))


def reject(client, auth, report_id, user, reason="Missing receipts"):
    return client.post(
        f"/reports/{report_id}/reject", json={"reason": reason}, headers=auth(user)
    )


def mark_paid(client, auth, report_id, user):
    return client.post(f"/reports/{report_id}/mark-paid", headers=auth(user))


# ----------------------------------------------------------------------------------
# The happy path
# ----------------------------------------------------------------------------------


def test_full_lifecycle_draft_to_paid(client, auth, make_report, employee, approver):
    report = make_report(employee)
    assert report["status"] == "draft"

    assert submit(client, auth, report, employee).json()["status"] == "submitted"
    assert approve(client, auth, report["id"], approver).json()["status"] == "approved"
    assert mark_paid(client, auth, report["id"], approver).json()["status"] == "paid"


def test_rejection_returns_the_report_to_draft(client, auth, make_report, employee, approver):
    """The brief: rejecting returns the report to Draft so its owner can fix and resubmit.

    The rejection itself stays in the timeline — returning to Draft must not erase it.
    """
    report = make_report(employee)
    submit(client, auth, report, employee)

    rejected = reject(client, auth, report["id"], approver, "Receipt missing")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "draft"

    timeline = client.get(f"/reports/{report['id']}/timeline", headers=auth(employee)).json()
    transitions = [(e["from_status"], e["to_status"]) for e in timeline]
    assert ("submitted", "rejected") in transitions
    assert ("rejected", "draft") in transitions
    assert any(e["reason"] == "Receipt missing" for e in timeline)

    # ...and it can go round again.
    assert submit(client, auth, report, employee).json()["status"] == "submitted"


# ----------------------------------------------------------------------------------
# Self-approval: the rule the brief states four separate times
# ----------------------------------------------------------------------------------


def test_approver_cannot_approve_their_own_report(client, auth, make_report, approver):
    report = make_report(approver)
    submit(client, auth, report, approver)

    response = approve(client, auth, report["id"], approver)

    assert response.status_code == 403
    assert "your own report" in response.json()["detail"].lower()


def test_approver_cannot_reject_their_own_report(client, auth, make_report, approver):
    report = make_report(approver)
    submit(client, auth, report, approver)

    response = reject(client, auth, report["id"], approver)

    assert response.status_code == 403
    assert "your own report" in response.json()["detail"].lower()


def test_approver_cannot_mark_their_own_report_paid(
    client, auth, make_report, approver, make_user
):
    """The self-approval rule covers mark-paid too, not just approve/reject."""
    other_approver = make_user(UserRole.approver, "Approver Two")
    report = make_report(approver)
    submit(client, auth, report, approver)
    approve(client, auth, report["id"], other_approver)

    response = mark_paid(client, auth, report["id"], approver)

    assert response.status_code == 403
    assert "your own report" in response.json()["detail"].lower()


def test_a_different_approver_can_decide_on_it(client, auth, make_report, approver, make_user):
    """"That report must wait for a different approver" — and then it goes through."""
    other_approver = make_user(UserRole.approver, "Approver Two")
    report = make_report(approver)
    submit(client, auth, report, approver)

    assert approve(client, auth, report["id"], other_approver).json()["status"] == "approved"


# ----------------------------------------------------------------------------------
# Role and ownership
# ----------------------------------------------------------------------------------


def test_employee_cannot_approve(client, auth, make_report, employee, make_user):
    other_employee = make_user(UserRole.employee, "Employee Two")
    report = make_report(employee)
    submit(client, auth, report, employee)

    response = approve(client, auth, report["id"], other_employee)

    assert response.status_code == 403
    assert "approver role" in response.json()["detail"].lower()


def test_only_the_owner_may_submit(client, auth, make_report, employee, make_user):
    other_employee = make_user(UserRole.employee, "Employee Two")
    report = make_report(employee)

    response = submit(client, auth, report, other_employee)

    assert response.status_code == 403
    assert "owner" in response.json()["detail"].lower()


def test_rejection_requires_a_reason(client, auth, make_report, employee, approver):
    report = make_report(employee)
    submit(client, auth, report, employee)

    blank = client.post(
        f"/reports/{report['id']}/reject", json={"reason": "   "}, headers=auth(approver)
    )
    missing = client.post(
        f"/reports/{report['id']}/reject", json={}, headers=auth(approver)
    )

    assert blank.status_code in (400, 422)
    assert missing.status_code == 422


def test_a_report_with_no_lines_cannot_be_submitted(client, auth, make_report, employee):
    report = make_report(employee, lines=[])

    response = submit(client, auth, report, employee)

    assert response.status_code == 400
    assert "at least one expense line" in response.json()["detail"]


# ----------------------------------------------------------------------------------
# Every illegal transition, and every refusal carrying a why
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "action", "expected_status"),
    [
        ("draft", "approve", 409),
        ("draft", "reject", 409),
        ("draft", "mark-paid", 409),
        ("submitted", "submit", 409),
        ("submitted", "mark-paid", 409),
        ("approved", "submit", 409),
        ("approved", "approve", 409),
        ("approved", "reject", 409),
        ("paid", "submit", 409),
        ("paid", "approve", 409),
        ("paid", "reject", 409),
        ("paid", "mark-paid", 409),
    ],
)
def test_illegal_transitions_are_refused_with_an_explanation(
    client, auth, make_report, employee, approver, state, action, expected_status
):
    report = make_report(employee)

    if state in {"submitted", "approved", "paid"}:
        submit(client, auth, report, employee)
    if state in {"approved", "paid"}:
        approve(client, auth, report["id"], approver)
    if state == "paid":
        mark_paid(client, auth, report["id"], approver)

    actor = employee if action == "submit" else approver
    body = {"reason": "no"} if action == "reject" else None
    response = client.post(
        f"/reports/{report['id']}/{action}", json=body, headers=auth(actor)
    )

    assert response.status_code == expected_status
    detail = response.json()["detail"]
    # Not just refused — refused with a message that says why.
    assert detail and state in detail.lower()
