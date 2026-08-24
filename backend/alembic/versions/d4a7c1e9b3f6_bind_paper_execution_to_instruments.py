"""bind paper execution to instruments

Revision ID: d4a7c1e9b3f6
Revises: c3f6a9b2d5e8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4a7c1e9b3f6"
down_revision: Union[str, Sequence[str], None] = "c3f6a9b2d5e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("execution_intents", sa.Column("instrument_id", sa.Uuid(), nullable=True))
    op.add_column(
        "execution_intents",
        sa.Column("instrument_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_execution_intents_instrument_identity_pair",
        "execution_intents",
        "(instrument_id IS NULL) = (instrument_snapshot IS NULL)",
    )
    op.create_check_constraint(
        "ck_execution_intents_instrument_snapshot_object",
        "execution_intents",
        "instrument_snapshot IS NULL OR jsonb_typeof(instrument_snapshot) = 'object'",
    )
    op.create_check_constraint(
        "ck_execution_intents_instrument_snapshot_size",
        "execution_intents",
        "instrument_snapshot IS NULL OR octet_length(instrument_snapshot::text) <= 4096",
    )
    op.create_index(op.f("ix_execution_intents_instrument_id"), "execution_intents", ["instrument_id"])
    op.create_foreign_key(
        "fk_execution_intents_instrument_id_instruments",
        "execution_intents",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION prevent_execution_intent_instrument_change() RETURNS trigger AS $$
        BEGIN
          IF OLD.instrument_id IS DISTINCT FROM NEW.instrument_id
             OR OLD.instrument_snapshot IS DISTINCT FROM NEW.instrument_snapshot THEN
            RAISE EXCEPTION 'Execution Intent Instrument snapshot is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_execution_intents_immutable_instrument
        BEFORE UPDATE ON execution_intents
        FOR EACH ROW EXECUTE FUNCTION prevent_execution_intent_instrument_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_execution_intents_immutable_instrument ON execution_intents")
    op.execute("DROP FUNCTION prevent_execution_intent_instrument_change()")
    op.drop_constraint("fk_execution_intents_instrument_id_instruments", "execution_intents", type_="foreignkey")
    op.drop_index(op.f("ix_execution_intents_instrument_id"), table_name="execution_intents")
    op.drop_constraint("ck_execution_intents_instrument_snapshot_size", "execution_intents", type_="check")
    op.drop_constraint("ck_execution_intents_instrument_snapshot_object", "execution_intents", type_="check")
    op.drop_constraint("ck_execution_intents_instrument_identity_pair", "execution_intents", type_="check")
    op.drop_column("execution_intents", "instrument_snapshot")
    op.drop_column("execution_intents", "instrument_id")
