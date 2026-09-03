"""Finding reports: search, filter, sort, pagination (goal 6).

All of it must happen on the server. The strongest evidence is pagination: if the browser
were filtering, `total` could not be right while `items` held only one page.
"""

from decimal import Decimal

from app.models.enums import UserRole

LINE = {
    "expense_date": "2026-08-02",
    "amount": "100.00",
    "category": "travel",
    "description": "Flight",
}


def test_pagination_reports_the_total_across_all_pages(
    client, auth, make_report, employee
):
    for index in range(25):
        make_report(employee, title=f"Trip {index:02d}")

    first = client.get("/reports?page=1&page_size=10", headers=auth(employee)).json()
    second = client.get("/reports?page=2&page_size=10", headers=auth(employee)).json()
    third = client.get("/reports?page=3&page_size=10", headers=auth(employee)).json()

    assert first["total"] == second["total"] == third["total"] == 25
    assert len(first["items"]) == 10
    assert len(third["items"]) == 5

    # No row appears on two pages, and none goes missing.
    ids = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(ids) == len(set(ids)) == 25


def test_search_matches_the_title(client, auth, make_report, employee):
    make_report(employee, title="Berlin client visit")
    make_report(employee, title="Munich conference")

    found = client.get("/reports?search=berlin", headers=auth(employee)).json()

    assert [item["title"] for item in found["items"]] == ["Berlin client visit"]
    assert found["total"] == 1


def test_filters_combine_with_and_not_or(
    client, auth, make_report, employee, approver, make_user
):
    other = make_user(UserRole.employee, "Employee Two")
    mine_submitted = make_report(employee, title="Mine submitted")
    make_report(employee, title="Mine draft")
    make_report(other, title="Theirs")
    client.post(f"/reports/{mine_submitted['id']}/submit", headers=auth(employee))

    result = client.get(
        f"/reports?status=submitted&owner_id={employee.id}", headers=auth(approver)
    ).json()

    assert [item["title"] for item in result["items"]] == ["Mine submitted"]


def test_filter_by_assigned_approver(client, auth, make_report, employee, approver, make_user):
    other_approver = make_user(UserRole.approver, "Approver Two")
    assigned = make_report(employee, title="Assigned")
    make_report(employee, title="Unassigned")
    client.post(
        f"/reports/{assigned['id']}/approvers",
        json={"approver_id": approver.id},
        headers=auth(employee),
    )

    mine = client.get("/reports?assigned_to_me=true", headers=auth(approver)).json()
    theirs = client.get("/reports?assigned_to_me=true", headers=auth(other_approver)).json()

    assert [item["title"] for item in mine["items"]] == ["Assigned"]
    assert theirs["items"] == []


def test_sorting_by_total(client, auth, make_report, employee):
    make_report(employee, title="Cheap", lines=[{**LINE, "amount": "10.00"}])
    make_report(employee, title="Expensive", lines=[{**LINE, "amount": "900.00"}])
    make_report(employee, title="Middling", lines=[{**LINE, "amount": "300.00"}])

    ascending = client.get("/reports?sort=total&direction=asc", headers=auth(employee)).json()
    descending = client.get("/reports?sort=total&direction=desc", headers=auth(employee)).json()

    assert [item["title"] for item in ascending["items"]] == ["Cheap", "Middling", "Expensive"]
    assert [item["title"] for item in descending["items"]] == ["Expensive", "Middling", "Cheap"]


def test_sorting_by_submitted_date(client, auth, make_report, employee):
    first = make_report(employee, title="First")
    second = make_report(employee, title="Second")
    client.post(f"/reports/{first['id']}/submit", headers=auth(employee))
    client.post(f"/reports/{second['id']}/submit", headers=auth(employee))

    result = client.get(
        "/reports?sort=submitted_at&direction=asc&status=submitted", headers=auth(employee)
    ).json()

    assert [item["title"] for item in result["items"]] == ["First", "Second"]


def test_an_unknown_sort_key_falls_back_instead_of_erroring(client, auth, make_report, employee):
    """The sort parameter is an allow-list, so it can never become arbitrary SQL."""
    make_report(employee)

    response = client.get("/reports?sort=title;DROP TABLE users", headers=auth(employee))

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_archived_reports_are_excluded_by_default(client, auth, make_report, employee):
    kept = make_report(employee, title="Active")
    archived = make_report(employee, title="Archived")
    client.post(f"/reports/{archived['id']}/archive", headers=auth(employee))

    default = client.get("/reports", headers=auth(employee)).json()
    including = client.get("/reports?include_archived=true", headers=auth(employee)).json()

    assert [item["title"] for item in default["items"]] == ["Active"]
    assert including["total"] == 2
    assert kept["id"] in [item["id"] for item in including["items"]]
