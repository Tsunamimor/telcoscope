"""add analytics.anomalies table

Revision ID: ffd972c2cd5a
Revises: b898c9323eda
Create Date: 2026-09-13 15:03:03.511328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ffd972c2cd5a'
down_revision: Union[str, Sequence[str], None] = 'b898c9323eda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create analytics.anomalies with indexes."""
    op.create_table(
        "anomalies",
        sa.Column("anomaly_uid", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("cell_id", sa.BigInteger(), nullable=False),
        sa.Column("kpi_name", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("detected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("anomaly_uid"),
        schema="analytics",
    )
    op.create_index(
        "ix_anomalies_cell_ts",
        "anomalies",
        ["cell_id", "ts"],
        schema="analytics",
    )
    op.create_index(
        "ix_anomalies_method_ts",
        "anomalies",
        ["method", "ts"],
        schema="analytics",
    )


def downgrade() -> None:
    """Drop analytics.anomalies and its indexes."""
    op.drop_index("ix_anomalies_method_ts", table_name="anomalies", schema="analytics")
    op.drop_index("ix_anomalies_cell_ts", table_name="anomalies", schema="analytics")
    op.drop_table("anomalies", schema="analytics")