"""harden historical retention

Revision ID: c6d1e8f3a9b2
Revises: b8e1c4d7f2a9
"""

from alembic import op


revision = "c6d1e8f3a9b2"
down_revision = "b8e1c4d7f2a9"
branch_labels = None
depends_on = None


def _replace(name, table, referred_table, columns, referred_columns, ondelete):
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        name, table, referred_table, columns, referred_columns, ondelete=ondelete
    )


def upgrade() -> None:
    _replace("strategies_creator_id_fkey", "strategies", "users", ["creator_id"], ["id"], "RESTRICT")
    _replace("backtests_strategy_version_id_fkey", "backtests", "strategy_versions", ["strategy_version_id"], ["id"], "RESTRICT")
    _replace("backtests_requested_by_user_id_fkey", "backtests", "users", ["requested_by_user_id"], ["id"], "RESTRICT")
    _replace("fk_allocation_intents_strategy_version_same_strategy", "allocation_intents", "strategy_versions", ["strategy_id", "strategy_version_id"], ["strategy_id", "id"], "RESTRICT")
    _replace("allocation_intents_investor_user_id_fkey", "allocation_intents", "users", ["investor_user_id"], ["id"], "RESTRICT")
    _replace("fk_execution_intents_strategy_version_same_strategy", "execution_intents", "strategy_versions", ["strategy_id", "strategy_version_id"], ["strategy_id", "id"], "RESTRICT")
    _replace("execution_intents_investor_user_id_fkey", "execution_intents", "users", ["investor_user_id"], ["id"], "RESTRICT")
    _replace("auth_sessions_user_id_fkey", "auth_sessions", "users", ["user_id"], ["id"], "CASCADE")


def downgrade() -> None:
    _replace("auth_sessions_user_id_fkey", "auth_sessions", "users", ["user_id"], ["id"], "RESTRICT")
    _replace("execution_intents_investor_user_id_fkey", "execution_intents", "users", ["investor_user_id"], ["id"], "CASCADE")
    _replace("fk_execution_intents_strategy_version_same_strategy", "execution_intents", "strategy_versions", ["strategy_id", "strategy_version_id"], ["strategy_id", "id"], "CASCADE")
    _replace("allocation_intents_investor_user_id_fkey", "allocation_intents", "users", ["investor_user_id"], ["id"], "CASCADE")
    _replace("fk_allocation_intents_strategy_version_same_strategy", "allocation_intents", "strategy_versions", ["strategy_id", "strategy_version_id"], ["strategy_id", "id"], "CASCADE")
    _replace("backtests_requested_by_user_id_fkey", "backtests", "users", ["requested_by_user_id"], ["id"], "CASCADE")
    _replace("backtests_strategy_version_id_fkey", "backtests", "strategy_versions", ["strategy_version_id"], ["id"], "CASCADE")
    _replace("strategies_creator_id_fkey", "strategies", "users", ["creator_id"], ["id"], "CASCADE")
