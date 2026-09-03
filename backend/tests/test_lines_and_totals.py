"""Expense lines and server-computed totals (goal 3)."""

from decimal import Decimal

from app.models.enums import UserRole

LINE = {
    "expense_date": "2026-08-02",
    "amount": "100.00",
    "category": "travel",
    "description": "Flight",
}


def test_total_is_the_sum_of_its_lines(client, auth, make_report, employee):
    report = make_report(
        employee,
        lines=[
            {**LINE, "amount": "100.00"},
            {**LINE, "amount": "25.50", "category": "meals"},
            {**LINE, "amount": "4.49", "category": "supplies"},
        ],
    )

    detail = client.get(f"/reports/{report['id']}", headers=auth(employee)).json()

    assert Decimal(detail["total"]) == Decimal("129.99")


def test_total_follows_the_lines_as_they_change(client, auth, make_report, employee):
    headers = auth(employee)
    report = make_report(employee, lines=[{**LINE, "amount": "100.00"}])
    report_id = report["id"]

    def total() -> Decimal:
        return Decimal(client.get(f"/reports/{report_id}", headers=headers).json()["total"])

    assert total() == Decimal("100.00")

    added = client.post(
        f"/reports/{report_id}/lines", json={**LINE, "amount": "50.00"}, headers=headers
    ).json()
    assert total() == Decimal("150.00")

    client.patch(
        f"/reports/{report_id}/lines/{added['id']}",
        json={"amount": "70.00"},
        headers=headers,
    )
    assert total() == Decimal("170.00")

    client.delete(f"/reports/{report_id}/lines/{added['id']}", headers=headers)
    assert total() == Decimal("100.00")


def test_a_client_supplied_total_is_ignored(client, auth, make_report, employee):
    """There is no writable total: the field simply does not exist on the way in."""
    report = make_report(employee, lines=[{**LINE, "amount": "10.00"}])

    client.patch(
        f"/reports/{report['id']}",
        json={"title": "Still fine", "total": "999999.00"},
        headers=auth(employee),
    )

    detail = client.get(f"/reports/{report['id']}", headers=auth(employee)).json()
    assert Decimal(detail["total"]) == Decimal("10.00")


def test_a_report_with_no_lines_totals_zero(client, auth, make_report, employee):
    report = make_report(employee, lines=[])

    detail = client.get(f"/reports/{report['id']}", headers=auth(employee)).json()

    assert Decimal(detail["total"]) == Decimal("0")


def test_lines_are_frozen_once_the_report_leaves_draft(
    client, auth, make_report, employee, approver
):
    headers = auth(employee)
    report = make_report(employee)
    line_id = client.get(f"/reports/{report['id']}", headers=headers).json()["lines"][0]["id"]

    client.post(f"/reports/{report['id']}/submit", headers=headers)

    assert client.post(f"/reports/{report['id']}/lines", json=LINE, headers=headers).status_code == 409
    assert (
        client.patch(
            f"/reports/{report['id']}/lines/{line_id}", json={"amount": "1.00"}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/reports/{report['id']}/lines/{line_id}", headers=headers).status_code
        == 409
    )


def test_lines_become_editable_again_after_a_rejection(
    client, auth, make_report, employee, approver
):
    """Rejection returns the report to Draft, so its owner really can fix it."""
    report = make_report(employee)
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))
    client.post(
        f"/reports/{report['id']}/reject", json={"reason": "Fix this"}, headers=auth(approver)
    )

    response = client.post(f"/reports/{report['id']}/lines", json=LINE, headers=auth(employee))

    assert response.status_code == 201


def test_only_the_owner_can_change_lines(client, auth, make_report, employee, approver):
    """Even an approver — who may *read* any report — cannot edit someone's lines."""
    report = make_report(employee)

    response = client.post(f"/reports/{report['id']}/lines", json=LINE, headers=auth(approver))

    assert response.status_code == 403


def test_invalid_lines_are_rejected(client, auth, make_report, employee):
    report = make_report(employee)
    headers = auth(employee)

    negative = client.post(
        f"/reports/{report['id']}/lines", json={**LINE, "amount": "-5.00"}, headers=headers
    )
    zero = client.post(
        f"/reports/{report['id']}/lines", json={**LINE, "amount": "0"}, headers=headers
    )
    bad_category = client.post(
        f"/reports/{report['id']}/lines", json={**LINE, "category": "yacht"}, headers=headers
    )
    empty_description = client.post(
        f"/reports/{report['id']}/lines", json={**LINE, "description": ""}, headers=headers
    )

    assert negative.status_code == 422
    assert zero.status_code == 422
    assert bad_category.status_code == 422
    assert empty_description.status_code == 422
