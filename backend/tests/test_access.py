"""Accounts, roles and visibility (goals 1 and 2).

The point of these tests is that the rules hold at the API, not in the interface: every
request here goes straight to the server, as a hostile client would.
"""

from app.models.enums import UserRole


def test_signup_and_login(client):
    signup = client.post(
        "/auth/signup",
        json={
            "email": "New.Person@Example.com",
            "full_name": "New Person",
            "password": "password123",
            "role": "employee",
        },
    )
    assert signup.status_code == 201
    # Emails are normalised, so the same address cannot register twice in different cases.
    assert signup.json()["user"]["email"] == "new.person@example.com"

    login = client.post(
        "/auth/login", json={"email": "NEW.PERSON@example.com", "password": "password123"}
    )
    assert login.status_code == 200


def test_duplicate_signup_is_refused(client, employee):
    response = client.post(
        "/auth/signup",
        json={
            "email": employee.email,
            "full_name": "Impostor",
            "password": "password123",
        },
    )
    assert response.status_code == 409


def test_wrong_password_is_rejected(client, employee):
    response = client.post(
        "/auth/login", json={"email": employee.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    # The same message either way, so the response cannot be used to enumerate accounts.
    assert response.json()["detail"] == "Incorrect email or password."


def test_protected_routes_require_a_token(client):
    assert client.get("/reports").status_code == 401
    assert client.get("/dashboard").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_a_forged_token_is_rejected(client):
    response = client.get("/reports", headers={"Authorization": "Bearer not.a.real.token"})
    assert response.status_code == 401


def test_employees_see_only_their_own_reports(
    client, auth, make_report, employee, make_user
):
    other = make_user(UserRole.employee, "Employee Two")
    make_report(employee, title="Mine")
    make_report(other, title="Theirs")

    visible = client.get("/reports", headers=auth(employee)).json()

    assert [item["title"] for item in visible["items"]] == ["Mine"]
    assert visible["total"] == 1


def test_an_employee_cannot_read_another_employees_report(
    client, auth, make_report, employee, make_user
):
    other = make_user(UserRole.employee, "Employee Two")
    theirs = make_report(other, title="Theirs")

    response = client.get(f"/reports/{theirs['id']}", headers=auth(employee))

    assert response.status_code == 403


def test_an_employee_cannot_widen_their_scope_with_a_filter(
    client, auth, make_report, employee, make_user
):
    """A filter parameter can narrow what you see. It must never widen it."""
    other = make_user(UserRole.employee, "Employee Two")
    make_report(other, title="Theirs")

    response = client.get(
        f"/reports?owner_id={other.id}", headers=auth(employee)
    ).json()

    assert response["items"] == []
    assert response["total"] == 0


def test_approvers_see_everyones_reports(client, auth, make_report, employee, approver):
    make_report(employee, title="Employee report")

    visible = client.get("/reports", headers=auth(approver)).json()

    assert "Employee report" in [item["title"] for item in visible["items"]]


def test_report_metadata_is_locked_once_submitted(client, auth, make_report, employee):
    report = make_report(employee)
    client.post(f"/reports/{report['id']}/submit", headers=auth(employee))

    response = client.patch(
        f"/reports/{report['id']}", json={"title": "Renamed"}, headers=auth(employee)
    )

    assert response.status_code == 409
    assert "Draft" in response.json()["detail"]


def test_archiving_hides_a_report_without_destroying_it(
    client, auth, make_report, employee
):
    report = make_report(employee, title="Old trip")
    client.post(f"/reports/{report['id']}/archive", headers=auth(employee))

    default_view = client.get("/reports", headers=auth(employee)).json()
    assert default_view["items"] == []

    # Still reachable, still whole.
    archived = client.get(
        "/reports?archived_only=true", headers=auth(employee)
    ).json()
    assert [item["title"] for item in archived["items"]] == ["Old trip"]

    detail = client.get(f"/reports/{report['id']}", headers=auth(employee)).json()
    assert detail["lines"] != []

    client.post(f"/reports/{report['id']}/restore", headers=auth(employee))
    assert client.get("/reports", headers=auth(employee)).json()["total"] == 1
