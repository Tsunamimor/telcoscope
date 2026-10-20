"""add analytics incidents table

Revision ID: 2d6b33dca0d9
Revises: ffd972c2cd5a
Create Date: 2026-10-12 19:44:47.382533

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2d6b33dca0d9'
down_revision: Union[str, Sequence[str], None] = 'ffd972c2cd5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cell_id", sa.Text, nullable=False),
        sa.Column("ts_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("detection_count", sa.Integer, nullable=False),
        sa.Column("methods", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("dominant_kpi", sa.Text),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="analytics",
    )

    op.create_index(
        "idx_incidents_cell_ts",
        "incidents",
        [sa.text("cell_id"), sa.text("ts_start DESC")],
        schema="analytics",
    )
    op.create_index(
        "idx_incidents_status",
        "incidents",
        ["status"],
        schema="analytics",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "idx_incidents_severity",
        "incidents",
        [sa.text("severity"), sa.text("ts_start DESC")],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index("idx_incidents_severity", table_name="incidents", schema="analytics")
    op.drop_index("idx_incidents_status", table_name="incidents", schema="analytics")
    op.drop_index("idx_incidents_cell_ts", table_name="incidents", schema="analytics")
    op.drop_table("incidents", schema="analytics")