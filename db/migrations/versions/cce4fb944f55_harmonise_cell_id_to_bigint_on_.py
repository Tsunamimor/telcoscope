"""harmonise cell_id to bigint on analytics tables

Revision ID: cce4fb944f55
Revises: 965647ef494d
Create Date: 2026-10-31 15:00:35.901859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cce4fb944f55'
down_revision: Union[str, Sequence[str], None] = '965647ef494d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop dbt marts that reference cell_id on either table.
    # mart_detector_evaluation is materialized as a TABLE;
    # mart_incidents_timeline as a VIEW.
    # Both will be rebuilt by `dbt build` after this migration.
    op.execute("DROP TABLE IF EXISTS dbt_dev_marts.mart_detector_evaluation CASCADE")
    op.execute("DROP VIEW IF EXISTS dbt_dev_marts.mart_incidents_timeline CASCADE")

    # Drop the UNIQUE index before changing the column type
    op.drop_index(
        "uq_incidents_cell_ts_start",
        table_name="incidents",
        schema="analytics",
    )

    # Alter cell_id on both tables (no-op on anomalies since already bigint).
    op.execute(
        "ALTER TABLE analytics.anomalies "
        "ALTER COLUMN cell_id TYPE BIGINT USING cell_id::BIGINT"
    )
    op.execute(
        "ALTER TABLE analytics.incidents "
        "ALTER COLUMN cell_id TYPE BIGINT USING cell_id::BIGINT"
    )

    # Recreate the UNIQUE index
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
    op.execute(
        "ALTER TABLE analytics.incidents "
        "ALTER COLUMN cell_id TYPE TEXT USING cell_id::TEXT"
    )
    op.execute(
        "ALTER TABLE analytics.anomalies "
        "ALTER COLUMN cell_id TYPE TEXT USING cell_id::TEXT"
    )
    op.create_index(
        "uq_incidents_cell_ts_start",
        "incidents",
        ["cell_id", "ts_start"],
        unique=True,
        schema="analytics",
    )