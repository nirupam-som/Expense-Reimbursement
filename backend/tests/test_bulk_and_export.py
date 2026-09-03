"""Bulk actions and the CSV export (goal 7).

The brief is specific about the bulk response: the server checks every report
individually, and the per-report result names any refused *because the approver owned
them*, alongside the other successes and refusals. That is what the mixed-batch test
pins down.
"""

import csv
import io
from decimal import Decimal

from app.models.enums import UserRole

LINE = {
    "expense_date": "2026-08-02",
    "amount": "100.00",
    "category": "travel",
    "description": "Flight",
}


def _submitted(client, auth, make_report, owner, title, amount="100.00"):
    report = make_report(owner, title=title, lines=[{**LINE, "amount": amount}])
    client.post(f"/reports/{report['id']}/submit", headers=auth(owner))
    return report


def test_bulk_approve_checks_every_report_individually(
    client, auth, make_report, approver, employee, make_user
):
    """A mixed batch: one fine, one owned by the approver, one in the wrong state."""
    other_employee = make_user(UserRole.employee, "Employee Two")

    ok = _submitted(client, auth, make_report, employee, "Someone else's")
    own = _submitted(client, auth, make_report, approver, "The approver's own")
    still_draft = make_report(other_employee, title="Never submitted")

    response = client.post(
        "/reports/bulk-approve",
        json={"report_ids": [ok["id"], own["id"], still_draft["id"]]},
        headers=auth(approver),
    )

    assert response.status_code == 200
    body = response.json()

    by_id = {item["report_id"]: item for item in body["results"]}
    assert by_id[ok["id"]]["outcome"] == "approved"

    # Refused specifically because the approver owns it — its own code, not lumped in
    # with the other refusals.
    assert by_id[own["id"]]["outcome"] == "refused"
    assert by_id[own["id"]]["refusal_code"] == "owner_is_approver"

    assert by_id[still_draft["id"]]["outcome"] == "refused"
    assert by_id[still_draft["id"]]["refusal_code"] == "wrong_status"

    assert body["succeeded"] == 1
    assert body["refused"] == 2
    assert body["owned_by_you"] == 1

    # And the partial success really was applied: it is not all-or-nothing.
    assert client.get(f"/reports/{ok['id']}", headers=auth(approver)).json()["status"] == "approved"
    assert client.get(f"/reports/{own['id']}", headers=auth(approver)).json()["status"] == "submitted"


def test_bulk_reject_requires_a_reason_and_records_it(
    client, auth, make_report, approver, employee
):
    report = _submitted(client, auth, make_report, employee, "Needs work")

    without_reason = client.post(
        "/reports/bulk-reject", json={"report_ids": [report["id"]]}, headers=auth(approver)
    )
    assert without_reason.status_code == 400

    with_reason = client.post(
        "/reports/bulk-reject",
        json={"report_ids": [report["id"]], "reason": "Receipts missing"},
        headers=auth(approver),
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["succeeded"] == 1

    timeline = client.get(f"/reports/{report['id']}/timeline", headers=auth(employee)).json()
    assert any(entry["reason"] == "Receipts missing" for entry in timeline)


def test_bulk_reports_unknown_ids_without_failing_the_batch(
    client, auth, make_report, approver, employee
):
    report = _submitted(client, auth, make_report, employee, "Real")

    body = client.post(
        "/reports/bulk-approve",
        json={"report_ids": [report["id"], 999_999]},
        headers=auth(approver),
    ).json()

    outcomes = {item["report_id"]: item["outcome"] for item in body["results"]}
    assert outcomes[report["id"]] == "approved"
    assert outcomes[999_999] == "not_found"


def test_bulk_requires_the_approver_role(client, auth, make_report, employee):
    report = make_report(employee)

    response = client.post(
        "/reports/bulk-approve", json={"report_ids": [report["id"]]}, headers=auth(employee)
    )

    assert response.status_code == 403


def test_csv_export_lists_approved_but_unpaid_reports(
    client, auth, make_report, approver, employee
):
    due = _submitted(client, auth, make_report, employee, "Awaiting payment", "250.00")
    already_paid = _submitted(client, auth, make_report, employee, "Settled", "75.00")
    still_submitted = _submitted(client, auth, make_report, employee, "Undecided", "999.00")

    client.post(f"/reports/{due['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{already_paid['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{already_paid['id']}/mark-paid", headers=auth(approver))

    response = client.get("/reports/export/unpaid.csv", headers=auth(approver))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(response.text)))
    titles = [row["Title"] for row in rows]

    assert titles == ["Awaiting payment"]  # not the paid one, not the undecided one
    assert Decimal(rows[0]["Amount Due"]) == Decimal("250.00")
    assert rows[0]["Owner"] == employee.full_name


def test_csv_export_is_valid_when_nothing_is_due(client, auth, approver):
    """An empty export is a header row, not an error."""
    response = client.get("/reports/export/unpaid.csv", headers=auth(approver))

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0] == "Report ID"
    assert len(rows) == 1


def test_csv_escapes_commas_and_quotes_in_titles(client, auth, make_report, approver, employee):
    awkward = 'Trip to "Paris", France'
    report = _submitted(client, auth, make_report, employee, awkward)
    client.post(f"/reports/{report['id']}/approve", headers=auth(approver))

    response = client.get("/reports/export/unpaid.csv", headers=auth(approver))

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["Title"] == awkward


def test_csv_export_requires_the_approver_role(client, auth, employee):
    assert client.get("/reports/export/unpaid.csv", headers=auth(employee)).status_code == 403
