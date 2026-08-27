"""rebrand synthetic instrument without changing its stable identity

Revision ID: e5a1b2c3d4f6
Revises: d4a7c1e9b3f6
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e5a1b2c3d4f6"
down_revision: Union[str, Sequence[str], None] = "d4a7c1e9b3f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE instruments
        SET canonical_symbol = 'ALGOPROFITX_TEST_EQ',
            exchange_symbol = 'ALGOPROFITX_TEST_EQ',
            name = 'AlgoProfitX Synthetic Reference Equity (not a real security)'
        WHERE id = '20000000-0000-4000-8000-000000000001'
          AND canonical_symbol = 'TRADEEBH_TEST_EQ'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE instruments
        SET canonical_symbol = 'TRADEEBH_TEST_EQ',
            exchange_symbol = 'TRADEEBH_TEST_EQ',
            name = 'TradeEBH Synthetic Reference Equity (not a real security)'
        WHERE id = '20000000-0000-4000-8000-000000000001'
          AND canonical_symbol = 'ALGOPROFITX_TEST_EQ'
        """
    )
