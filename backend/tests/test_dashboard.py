"""Dashboard aggregates (goal 8).

Each figure is asserted against a hand-computed expectation rather than against whatever
the code happens to return.
"""

from decimal import Decimal

from app.models.enums import UserRole

LINE = {
    "expense_date": "2026-08-02",
    "amount": "100.00",
    "category": "travel",
    "description": "Flight",
}


def _submitted(client, auth, make_report, owner, title, amount, category="travel"):
    report = make_report(
        owner, title=title, lines=[{**LINE, "amount": amount, "category": category}]
    )
    client.post(f"/reports/{report['id']}/submit", headers=auth(owner))
    return report


def test_headline_numbers(client, auth, make_report, employee, approver):
    awaiting = _submitted(client, auth, make_report, employee, "Awaiting", "150.00")
    due = _submitted(client, auth, make_report, employee, "Due", "200.00")
    settled = _submitted(client, auth, make_report, employee, "Settled", "75.00")

    client.post(f"/reports/{due['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{settled['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{settled['id']}/mark-paid", headers=auth(approver))

    dashboard = client.get("/dashboard", headers=auth(approver)).json()

    assert dashboard["awaiting_approval"] == 1
    # Approved but not yet paid — the paid one no longer counts as owed.
    assert Decimal(dashboard["total_due"]) == Decimal("200.00")
    # Both approvals happened this week; one of them was also paid this week.
    assert dashboard["approved_this_week"] == 2
    assert dashboard["paid_this_week"] == 1
    assert awaiting["id"] is not None


def test_breakdown_by_status_covers_every_status(client, auth, make_report, employee, approver):
    _submitted(client, auth, make_report, employee, "Submitted", "10.00")
    make_report(employee, title="A draft")

    dashboard = client.get("/dashboard", headers=auth(approver)).json()
    counts = {row["status"]: row["count"] for row in dashboard["by_status"]}

    assert counts["draft"] == 1
    assert counts["submitted"] == 1
    # Statuses with nothing in them are still present, as zero.
    assert counts["approved"] == 0
    assert counts["paid"] == 0
    assert counts["rejected"] == 0


def test_breakdown_by_category_sums_lines_not_reports(
    client, auth, make_report, employee, approver
):
    """A report can span categories, so the breakdown is per line."""
    make_report(
        employee,
        title="Mixed",
        lines=[
            {**LINE, "amount": "300.00", "category": "travel"},
            {**LINE, "amount": "120.00", "category": "meals"},
            {**LINE, "amount": "80.00", "category": "meals"},
        ],
    )

    dashboard = client.get("/dashboard", headers=auth(approver)).json()
    by_category = {row["category"]: row for row in dashboard["by_category"]}

    assert Decimal(by_category["travel"]["total"]) == Decimal("300.00")
    assert Decimal(by_category["meals"]["total"]) == Decimal("200.00")
    assert by_category["meals"]["line_count"] == 2
    assert Decimal(by_category["lodging"]["total"]) == Decimal("0")


def test_weekly_chart_always_has_eight_zero_filled_weeks(client, auth, approver):
    dashboard = client.get("/dashboard", headers=auth(approver)).json()
    weeks = dashboard["weekly_paid"]

    assert len(weeks) == 8
    # Weeks with no payments are present as zero rather than skipped — a chart that
    # omitted them would misrepresent the trend.
    assert all(Decimal(week["total"]) == Decimal("0") for week in weeks)
    assert [week["week_start"] for week in weeks] == sorted(week["week_start"] for week in weeks)


def test_payments_land_in_the_current_week_bucket(
    client, auth, make_report, employee, approver
):
    paid = _submitted(client, auth, make_report, employee, "Paid now", "425.00")
    client.post(f"/reports/{paid['id']}/approve", headers=auth(approver))
    client.post(f"/reports/{paid['id']}/mark-paid", headers=auth(approver))

    weeks = client.get("/dashboard", headers=auth(approver)).json()["weekly_paid"]

    assert Decimal(weeks[-1]["total"]) == Decimal("425.00")
    assert sum(Decimal(week["total"]) for week in weeks) == Decimal("425.00")


def test_an_employees_dashboard_only_counts_their_own_reports(
    client, auth, make_report, employee, approver, make_user
):
    other = make_user(UserRole.employee, "Employee Two")
    _submitted(client, auth, make_report, employee, "Mine", "100.00")
    _submitted(client, auth, make_report, other, "Theirs", "500.00")

    mine = client.get("/dashboard", headers=auth(employee)).json()
    everything = client.get("/dashboard", headers=auth(approver)).json()

    assert mine["awaiting_approval"] == 1
    assert everything["awaiting_approval"] == 2


def test_archived_reports_are_excluded_from_the_dashboard(
    client, auth, make_report, employee, approver
):
    report = _submitted(client, auth, make_report, employee, "Old", "100.00")
    before = client.get("/dashboard", headers=auth(approver)).json()["awaiting_approval"]

    client.post(f"/reports/{report['id']}/archive", headers=auth(employee))
    after = client.get("/dashboard", headers=auth(approver)).json()["awaiting_approval"]

    assert (before, after) == (1, 0)
