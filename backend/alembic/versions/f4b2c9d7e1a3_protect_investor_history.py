"""protect investor history

Revision ID: f4b2c9d7e1a3
Revises: e3f8a1c5d2b6
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f4b2c9d7e1a3"
down_revision: Union[str, Sequence[str], None] = "e3f8a1c5d2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "allocation_intents_strategy_id_fkey",
        "allocation_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_allocation_intents_strategy",
        "allocation_intents",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "execution_intents_strategy_id_fkey",
        "execution_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_execution_intents_strategy",
        "execution_intents",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_execution_intents_strategy",
        "execution_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "execution_intents_strategy_id_fkey",
        "execution_intents",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_allocation_intents_strategy",
        "allocation_intents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "allocation_intents_strategy_id_fkey",
        "allocation_intents",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="CASCADE",
    )
