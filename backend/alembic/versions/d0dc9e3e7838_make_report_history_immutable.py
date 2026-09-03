"""make report history immutable

Goal 9 requires that nothing in a report's timeline can be edited or deleted after the
fact, *including by approvers*. The application already offers no route that would do it —
but "we didn't build that endpoint" is a promise about today's code, not a guarantee.

This migration makes the database refuse the operation outright. A BEFORE UPDATE OR DELETE
trigger is used rather than REVOKE, because REVOKE only binds roles other than the table's
owner, and in a single-role deployment (which the free hosting tiers encourage) the
application connects as the owner. The trigger holds for every non-superuser regardless of
how roles are set up, which makes it the portable guarantee.

Revision ID: d0dc9e3e7838
Revises: f4dbe2a9b664
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d0dc9e3e7838"
down_revision: str | Sequence[str] | None = "f4dbe2a9b664"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("report_events", "report_comments")


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_history_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'Report history is append-only: % on % is not permitted',
                TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_history_mutation();
            """
        )


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    op.execute("DROP FUNCTION IF EXISTS reject_history_mutation();")
