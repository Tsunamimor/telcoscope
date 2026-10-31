"""add_rca_hypotheses_table

Revision ID: <alembic generated — don't change>
Revises: cce4fb944f55
Create Date: 2026-10-31 ...

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "<alembic generated>"
down_revision: str | None = "cce4fb944f55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create analytics.rca_hypotheses table.

    One row per (incident, hypothesis_rank). The engine upserts here
    after evaluating the rule library against an incident; downstream
    (narrator, Grafana) reads from this table.
    """
    op.create_table(
        "rca_hypotheses",
        sa.Column(
    "incident_id",
    sa.dialects.postgresql.UUID(as_uuid=True),
    nullable=False,
),
        sa.Column("hypothesis_rank", sa.Integer, nullable=False),
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column(
            "confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            sa.dialects.postgresql.JSONB,
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "hypothesis_rank",
            name="pk_rca_hypotheses",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["analytics.incidents.incident_id"],
            name="fk_rca_hypotheses_incident",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_rca_hypotheses_confidence_range",
        ),
        sa.CheckConstraint(
            "hypothesis_rank >= 1",
            name="ck_rca_hypotheses_rank_positive",
        ),
        schema="analytics",
    )


    # Index for "how often does rule X fire?" (rule performance
    # analysis).
    op.create_index(
        "ix_rca_hypotheses_rule_id",
        "rca_hypotheses",
        ["rule_id"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rca_hypotheses_rule_id",
        table_name="rca_hypotheses",
        schema="analytics",
    )

    op.drop_table("rca_hypotheses", schema="analytics")