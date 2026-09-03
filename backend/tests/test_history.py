"""The immutable timeline (goal 9), and assigned approvers (goal 5)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from app.models.enums import UserRole


def test_the_timeline_records_every_transition_with_who_and_why(
    client, auth, make_report, employee, approver
):
    report = make_report(employee)
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    client.post(
        f"/reports/{report['id']}/reject",
        json={"reason": "Receipt missing"},
        headers=auth(approver),
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    client.post(f"/reports/{report['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{report['id']}/mark-paid", headers=auth(approver))

    timeline = client.get(f"/reports/{report['id']}/timeline", headers=auth(employee)).json()
    transitions = [(e["from_status"], e["to_status"]) for e in timeline if e["kind"] == "status_change"]

    assert transitions == [
        ("draft", "submitted"),
        ("submitted", "rejected"),
        ("rejected", "draft"),
        ("draft", "submitted"),
        ("submitted", "approved"),
        ("approved", "paid"),
    ]

    rejection = next(e for e in timeline if e["to_status"] == "rejected")
    assert rejection["reason"] == "Receipt missing"
    assert rejection["actor"]["id"] == approver.id

    submission = next(e for e in timeline if e["to_status"] == "submitted")
    assert submission["actor"]["id"] == employee.id


def test_comments_appear_in_the_timeline(client, auth, make_report, employee, approver):
    report = make_report(employee)

    client.post(
        f"/reports/{report['id']}/comments",
        json={"body": "Flight was rebooked, hence the price."},
        headers=auth(employee),
    )
    client.post(
        f"/reports/{report['id']}/comments",
        json={"body": "Understood, thanks."},
        headers=auth(approver),
    )

    timeline = client.get(f"/reports/{report['id']}/timeline", headers=auth(employee)).json()
    comments = [e for e in timeline if e["kind"] == "comment"]

    assert [c["body"] for c in comments] == [
        "Flight was rebooked, hence the price.",
        "Understood, thanks.",
    ]
    assert comments[1]["actor"]["id"] == approver.id


def test_there_is_no_route_that_edits_or_deletes_history(client, auth, make_report, employee, approver):
    """Immutability, first layer: the capability does not exist in the API at all."""
    report = make_report(employee)
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    comment = client.post(
        f"/reports/{report['id']}/comments", json={"body": "Original"}, headers=auth(employee)
    ).json()

    headers = auth(approver)  # even the privileged role has nothing to call
    for method, path in [
        ("patch", f"/reports/{report['id']}/comments/{comment['id']}"),
        ("delete", f"/reports/{report['id']}/comments/{comment['id']}"),
        ("patch", f"/reports/{report['id']}/timeline/1"),
        ("delete", f"/reports/{report['id']}/timeline/1"),
    ]:
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code in (404, 405), f"{method} {path} should not exist"


@pytest.mark.parametrize("table", ["report_events", "report_comments"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_the_database_itself_refuses_to_rewrite_history(
    client, auth, make_report, db, employee, approver, table, operation
):
    """Immutability, second layer: even raw SQL cannot do it.

    This is what makes the guarantee hold against a future bug rather than only against
    today's route list.
    """
    report = make_report(employee)
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    client.post(
        f"/reports/{report['id']}/comments", json={"body": "Original"}, headers=auth(employee)
    )

    statement = (
        f"UPDATE {table} SET created_at = now()"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )

    with pytest.raises(DatabaseError, match="append-only"):
        db.execute(text(statement))
        db.commit()

    db.rollback()


# ----------------------------------------------------------------------------------
# Assigned approvers (goal 5)
# ----------------------------------------------------------------------------------


def test_a_report_can_have_many_approvers_and_an_approver_many_reports(
    client, auth, make_report, employee, approver, make_user
):
    second_approver = make_user(UserRole.approver, "Approver Two")
    first_report = make_report(employee, title="One")
    second_report = make_report(employee, title="Two")

    for report in (first_report, second_report):
        for person in (approver, second_approver):
            response = client.post(
                f"/reports/{report['id']}/approvers",
                json={"approver_id": person.id},
                headers=auth(employee),
            )
            assert response.status_code == 201

    assigned = client.get(
        f"/reports/{first_report['id']}/approvers", headers=auth(employee)
    ).json()
    assert {person["id"] for person in assigned} == {approver.id, second_approver.id}

    queue = client.get("/reports?assigned_to_me=true", headers=auth(approver)).json()
    assert queue["total"] == 2


def test_assigning_the_same_approver_twice_is_harmless(
    client, auth, make_report, employee, approver
):
    report = make_report(employee)
    payload = {"approver_id": approver.id}

    client.post(f"/reports/{report['id']}/approvers", json=payload, headers=auth(employee))
    second = client.post(
        f"/reports/{report['id']}/approvers", json=payload, headers=auth(employee)
    )

    assert second.status_code == 201
    assert len(second.json()) == 1


def test_only_approvers_can_be_assigned(client, auth, make_report, employee, make_user):
    plain_employee = make_user(UserRole.employee, "Employee Two")
    report = make_report(employee)

    response = client.post(
        f"/reports/{report['id']}/approvers",
        json={"approver_id": plain_employee.id},
        headers=auth(employee),
    )

    assert response.status_code == 400
    assert "approver role" in response.json()["detail"]


def test_any_approver_may_decide_even_when_unassigned(
    client, auth, make_report, employee, approver, make_user
):
    """Assignment routes work; it is not an authorization gate (Decision 6)."""
    assigned_approver = make_user(UserRole.approver, "Approver Two")
    report = make_report(employee)
    client.post(
        f"/reports/{report['id']}/approvers",
        json={"approver_id": assigned_approver.id},
        headers=auth(employee),
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))

    response = client.post(f"/reports/{report['id']}/approve", headers=auth(approver))

    assert response.status_code == 200


def test_unassigning_leaves_history_untouched(
    client, auth, make_report, employee, approver
):
    report = make_report(employee)
    client.post(
        f"/reports/{report['id']}/approvers",
        json={"approver_id": approver.id},
        headers=auth(employee),
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    client.post(f"/reports/{report['id']}/approve", headers=auth(approver))

    client.delete(
        f"/reports/{report['id']}/approvers/{approver.id}", headers=auth(employee)
    )

    timeline = client.get(f"/reports/{report['id']}/timeline", headers=auth(employee)).json()
    assert any(
        e["to_status"] == "approved" and e["actor"]["id"] == approver.id for e in timeline
    )
