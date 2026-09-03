"""Demo data, so the deployed app shows the system doing something rather than an
empty shell.

Run with:  python -m app.seed

Every report reaches its state through the *real* transition functions, not by writing
statuses directly. That guarantees the demo data is reachable by legal moves and that its
timeline is genuine — the history you see is the history the rules actually produced.

Deliberately included, because they are what the system is for:
  - a stale report nobody has decided on (drives the alert badge)
  - an approver's own report, which they are blocked from approving themselves
  - a rejected report that returned to Draft, with the rejection still in its timeline
  - payments spread over the last eight weeks, so the dashboard chart has a shape
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import ExpenseLine, ExpenseReport, ReportApprover, ReportComment, User
from app.models.enums import ExpenseCategory, UserRole
from app.services.lifecycle import Action, apply_transition

NOW = datetime.now(timezone.utc)
DEMO_PASSWORD = "password123"

TABLES = (
    "report_comments",
    "report_events",
    "stale_alert_dismissals",
    "report_approvers",
    "expense_lines",
    "expense_reports",
    "users",
)


def reset(db: Session) -> None:
    """TRUNCATE, not DELETE: row-level triggers make the history tables undeletable, and
    TRUNCATE is the admin-level operation that is allowed to reset them."""
    db.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    db.commit()


def make_user(db: Session, email: str, name: str, role: UserRole) -> User:
    user = User(
        email=email,
        full_name=name,
        password_hash=hash_password(DEMO_PASSWORD),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def make_report(
    db: Session,
    *,
    owner: User,
    title: str,
    start: date,
    end: date,
    lines: list[tuple[str, str, ExpenseCategory, str]],
    approvers: list[User],
    journey: list[tuple[Action, User, datetime, str | None]] | None = None,
    archived: bool = False,
) -> ExpenseReport:
    report = ExpenseReport(
        owner_id=owner.id, title=title, date_range_start=start, date_range_end=end
    )
    db.add(report)
    db.flush()

    for line_date, amount, category, description in lines:
        db.add(
            ExpenseLine(
                report_id=report.id,
                expense_date=date.fromisoformat(line_date),
                amount=Decimal(amount),
                category=category,
                description=description,
            )
        )

    for approver in approvers:
        db.add(ReportApprover(report_id=report.id, approver_id=approver.id))

    db.flush()

    for action, actor, at, reason in journey or []:
        outcome = apply_transition(
            db, report=report, action=action, actor=actor, reason=reason, at=at
        )
        if not outcome.allowed:  # pragma: no cover - a seed bug, surface it loudly
            raise RuntimeError(f"Seed journey illegal for {title!r}: {outcome.message}")
        db.flush()

    report.is_archived = archived
    db.flush()
    return report


def seed() -> None:
    with SessionLocal() as db:
        reset(db)

        # --- people ----------------------------------------------------------------
        priya = make_user(db, "priya@acme.com", "Priya Sharma", UserRole.approver)
        daniel = make_user(db, "daniel@acme.com", "Daniel Okafor", UserRole.approver)
        aisha = make_user(db, "aisha@acme.com", "Aisha Khan", UserRole.employee)
        marco = make_user(db, "marco@acme.com", "Marco Rossi", UserRole.employee)
        lena = make_user(db, "lena@acme.com", "Lena Fischer", UserRole.employee)
        tom = make_user(db, "tom@acme.com", "Tom Becker", UserRole.employee)
        db.flush()

        def paid_journey(approver: User, submitted: int, approved: int, paid: int):
            return [
                (Action.submit, None, days_ago(submitted), None),
                (Action.approve, approver, days_ago(approved), None),
                (Action.mark_paid, approver, days_ago(paid), None),
            ]

        def owned(journey, owner: User):
            """Fill in the owner as the actor for the submit step."""
            return [(a, actor or owner, at, r) for a, actor, at, r in journey]

        # --- paid reports, spread across the last eight weeks (dashboard chart) ------
        make_report(
            db,
            owner=aisha,
            title="Client visit — Berlin",
            start=date(2026, 7, 20),
            end=date(2026, 7, 24),
            lines=[
                ("2026-07-20", "412.60", ExpenseCategory.travel, "Flight BER return"),
                ("2026-07-20", "268.00", ExpenseCategory.lodging, "Hotel, 2 nights"),
                ("2026-07-22", "64.30", ExpenseCategory.meals, "Client dinner"),
            ],
            approvers=[priya],
            journey=owned(paid_journey(priya, 48, 46, 44), aisha),
        )
        make_report(
            db,
            owner=marco,
            title="Q3 sales trip — Milan",
            start=date(2026, 7, 28),
            end=date(2026, 7, 31),
            lines=[
                ("2026-07-28", "310.00", ExpenseCategory.travel, "Rail, Milan return"),
                ("2026-07-29", "395.00", ExpenseCategory.lodging, "Hotel, 3 nights"),
                ("2026-07-30", "88.50", ExpenseCategory.meals, "Team dinner with reseller"),
            ],
            approvers=[priya, daniel],
            journey=owned(paid_journey(daniel, 40, 38, 37), marco),
        )
        make_report(
            db,
            owner=lena,
            title="Conference — Amsterdam",
            start=date(2026, 8, 11),
            end=date(2026, 8, 14),
            lines=[
                ("2026-08-11", "540.00", ExpenseCategory.travel, "Flights AMS"),
                ("2026-08-11", "610.00", ExpenseCategory.lodging, "Conference hotel"),
                ("2026-08-12", "72.00", ExpenseCategory.transportation, "Airport transfers"),
            ],
            approvers=[priya],
            journey=owned(paid_journey(priya, 26, 24, 22), lena),
        )
        make_report(
            db,
            owner=tom,
            title="Office supplies — Q3 restock",
            start=date(2026, 8, 24),
            end=date(2026, 8, 26),
            lines=[
                ("2026-08-24", "184.20", ExpenseCategory.supplies, "Monitor stands ×4"),
                ("2026-08-25", "96.75", ExpenseCategory.supplies, "Stationery and cables"),
            ],
            approvers=[daniel],
            journey=owned(paid_journey(daniel, 12, 10, 8), tom),
        )
        make_report(
            db,
            owner=aisha,
            title="Team offsite — Lisbon",
            start=date(2026, 8, 29),
            end=date(2026, 8, 31),
            lines=[
                ("2026-08-29", "489.00", ExpenseCategory.travel, "Flights LIS"),
                ("2026-08-29", "355.00", ExpenseCategory.lodging, "Offsite accommodation"),
                ("2026-08-30", "142.80", ExpenseCategory.meals, "Team meals, 2 days"),
            ],
            approvers=[priya],
            journey=owned(paid_journey(priya, 6, 3, 1), aisha),
        )

        # --- approved but unpaid: this is the "reimbursements due" figure ------------
        make_report(
            db,
            owner=marco,
            title="Customer onboarding — Munich",
            start=date(2026, 8, 25),
            end=date(2026, 8, 27),
            lines=[
                ("2026-08-25", "228.40", ExpenseCategory.travel, "Rail to Munich"),
                ("2026-08-25", "290.00", ExpenseCategory.lodging, "Hotel, 2 nights"),
                ("2026-08-26", "51.20", ExpenseCategory.meals, "Lunch with customer"),
            ],
            approvers=[priya, daniel],
            journey=[
                (Action.submit, marco, days_ago(9), None),
                (Action.approve, priya, days_ago(7), None),
            ],
        )
        make_report(
            db,
            owner=lena,
            title="Advanced Postgres training",
            start=date(2026, 8, 18),
            end=date(2026, 8, 20),
            lines=[
                ("2026-08-18", "950.00", ExpenseCategory.other, "Course fee"),
                ("2026-08-18", "120.00", ExpenseCategory.transportation, "Travel to venue"),
            ],
            approvers=[daniel],
            journey=[
                (Action.submit, lena, days_ago(11), None),
                (Action.approve, daniel, days_ago(5), None),
            ],
        )

        # --- stale: submitted, still undecided, past the alert threshold -------------
        make_report(
            db,
            owner=tom,
            title="Airport transfers — August",
            start=date(2026, 8, 3),
            end=date(2026, 8, 21),
            lines=[
                ("2026-08-03", "62.00", ExpenseCategory.transportation, "Taxi to airport"),
                ("2026-08-21", "58.50", ExpenseCategory.transportation, "Taxi from airport"),
            ],
            approvers=[priya, daniel],
            journey=[(Action.submit, tom, days_ago(12), None)],
        )
        make_report(
            db,
            owner=aisha,
            title="Hardware refresh — laptop dock",
            start=date(2026, 8, 15),
            end=date(2026, 8, 15),
            lines=[
                ("2026-08-15", "245.00", ExpenseCategory.supplies, "Thunderbolt dock"),
                ("2026-08-15", "39.90", ExpenseCategory.supplies, "USB-C cables"),
            ],
            approvers=[daniel],
            journey=[(Action.submit, aisha, days_ago(8), None)],
        )

        # --- recently submitted: awaiting approval, not yet stale --------------------
        make_report(
            db,
            owner=marco,
            title="Client meals — early September",
            start=date(2026, 9, 1),
            end=date(2026, 9, 2),
            lines=[
                ("2026-09-01", "78.00", ExpenseCategory.meals, "Dinner, prospect"),
                ("2026-09-02", "44.10", ExpenseCategory.meals, "Breakfast meeting"),
            ],
            approvers=[priya],
            journey=[(Action.submit, marco, days_ago(1), None)],
        )

        # --- an approver's own report: they cannot decide on it themselves -----------
        make_report(
            db,
            owner=priya,
            title="Approver's own trip — Vienna",
            start=date(2026, 8, 27),
            end=date(2026, 8, 29),
            lines=[
                ("2026-08-27", "356.00", ExpenseCategory.travel, "Flights VIE"),
                ("2026-08-27", "240.00", ExpenseCategory.lodging, "Hotel, 2 nights"),
            ],
            # Assigned to the other approver, since Priya cannot decide on her own report.
            approvers=[daniel],
            journey=[(Action.submit, priya, days_ago(4), None)],
        )

        # --- rejected, and therefore back in Draft, with the rejection still on record
        rejected = make_report(
            db,
            owner=tom,
            title="Weekend car hire",
            start=date(2026, 8, 8),
            end=date(2026, 8, 10),
            lines=[
                ("2026-08-08", "310.00", ExpenseCategory.transportation, "Car hire, 3 days"),
                ("2026-08-09", "68.00", ExpenseCategory.other, "Fuel"),
            ],
            approvers=[priya],
            journey=[
                (Action.submit, tom, days_ago(20), None),
                (
                    Action.reject,
                    priya,
                    days_ago(18),
                    "Weekend car hire needs prior sign-off, and the fuel receipt is "
                    "missing. Please attach it and resubmit.",
                ),
            ],
        )
        db.add(
            ReportComment(
                report_id=rejected.id,
                author_id=tom.id,
                body="Understood — chasing the receipt from the rental desk now.",
                created_at=days_ago(17),
            )
        )

        # --- a draft that has never been submitted -----------------------------------
        make_report(
            db,
            owner=lena,
            title="September travel (in progress)",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            lines=[("2026-09-02", "112.00", ExpenseCategory.travel, "Rail season extension")],
            approvers=[],
        )

        # --- archived: out of the default view, history intact ------------------------
        make_report(
            db,
            owner=aisha,
            title="Client visit — Prague (last quarter)",
            start=date(2026, 6, 9),
            end=date(2026, 6, 12),
            lines=[
                ("2026-06-09", "298.00", ExpenseCategory.travel, "Flights PRG"),
                ("2026-06-09", "210.00", ExpenseCategory.lodging, "Hotel, 3 nights"),
            ],
            approvers=[priya],
            journey=owned(paid_journey(priya, 80, 78, 75), aisha),
            archived=True,
        )

        db.commit()

        print("Seeded demo data.")
        print(f"  users:   {db.query(User).count()}")
        print(f"  reports: {db.query(ExpenseReport).count()}")
        print(f"  lines:   {db.query(ExpenseLine).count()}")
        print(f"\nEveryone signs in with the password: {DEMO_PASSWORD}")
        print("  approvers: priya@acme.com, daniel@acme.com")
        print("  employees: aisha@acme.com, marco@acme.com, lena@acme.com, tom@acme.com")


if __name__ == "__main__":
    seed()
    engine.dispose()
