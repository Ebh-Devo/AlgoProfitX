"""add paper execution results

Revision ID: e3f8a1c5d2b6
Revises: b7d3f9e1c2a4
Create Date: 2026-08-21 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e3f8a1c5d2b6"
down_revision: Union[str, Sequence[str], None] = "b7d3f9e1c2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "execution_intents",
        sa.Column("paper_result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_constraint(
        "execution_intents_allocation_intent_id_fkey",
        "execution_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_execution_intents_allocation_intent",
        "execution_intents",
        "allocation_intents",
        ["allocation_intent_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_execution_intents_allocation_intent",
        "execution_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "execution_intents_allocation_intent_id_fkey",
        "execution_intents",
        "allocation_intents",
        ["allocation_intent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("execution_intents", "paper_result_summary")
