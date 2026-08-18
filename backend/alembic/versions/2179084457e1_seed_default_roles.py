
"""seed default roles

Revision ID: 2179084457e1
Revises: 0e5e28f41550
Create Date: ...
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "2179084457e1"
down_revision: Union[str, Sequence[str], None] = "0e5e28f41550"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
    )

    op.bulk_insert(
        roles_table,
        [
            {"id": uuid.uuid4(), "name": "ADMIN"},
            {"id": uuid.uuid4(), "name": "CREATOR"},
            {"id": uuid.uuid4(), "name": "INVESTOR"},
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM roles WHERE name IN "
            "('ADMIN', 'CREATOR', 'INVESTOR')"
        )
    )