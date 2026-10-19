"""unique index on incidents cell_id ts_start

Revision ID: 965647ef494d
Revises: 2d6b33dca0d9
Create Date: 2026-10-13 20:32:48.054472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '965647ef494d'
down_revision: Union[str, Sequence[str], None] = '2d6b33dca0d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_incidents_cell_ts_start",
        "incidents",
        ["cell_id", "ts_start"],
        unique=True,
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_incidents_cell_ts_start",
        table_name="incidents",
        schema="analytics",
    )
