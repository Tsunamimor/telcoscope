"""convert to hypertables and add indexes

Revision ID: b898c9323eda
Revises: ba8e9613d44b
Create Date: 2026-08-26 06:22:41.443303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b898c9323eda'
down_revision: Union[str, Sequence[str], None] = 'ba8e9613d44b'
branch_labels = None
depends_on = None   


def upgrade() -> None:
    # --- pm_measurements ---
    op.execute(
        """
        SELECT create_hypertable(
            'raw.pm_measurements',
            'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pm_measurements_cell_counter_ts
        ON raw.pm_measurements (cell_id, counter_id, ts DESC);
        """
    )


    # --- fm_alarms ---
    # Timescale requires the partitioning column to be part of the primary key.
    # Swap the alarm_uid-only PK for a composite (alarm_uid, raised_at) PK
    # before converting to a hypertable.
    op.execute("ALTER TABLE raw.fm_alarms DROP CONSTRAINT fm_alarms_pkey;")
    op.execute("ALTER TABLE raw.fm_alarms ADD PRIMARY KEY (alarm_uid, raised_at);")

    op.execute(
        """
        SELECT create_hypertable(
            'raw.fm_alarms',
            'raised_at',
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE,
            migrate_data => TRUE
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_alarms_cell_raised
        ON raw.fm_alarms (cell_id, raised_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_alarms_enb_raised
        ON raw.fm_alarms (enb_id, raised_at DESC);
        """
    )
    
    # --- cm_changes ---
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cm_changes_cell_time
        ON raw.cm_changes (cell_id, changed_at DESC);
        """
    )
    

    # --- synth_truth ---
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_synth_truth_cell_ts
        ON analytics.synth_truth (cell_id, ts_start);
        """
    )


def downgrade() -> None:
    # Drop indexes (hypertable → regular table conversion is more involved
    # and rarely needed in dev; leave the tables as hypertables on downgrade).
    op.execute("DROP INDEX IF EXISTS raw.ix_pm_measurements_cell_counter_ts;")
    op.execute("DROP INDEX IF EXISTS raw.ix_fm_alarms_cell_raised;")
    op.execute("DROP INDEX IF EXISTS raw.ix_fm_alarms_enb_raised;")
    op.execute("DROP INDEX IF EXISTS raw.ix_cm_changes_cell_time;")
    op.execute("DROP INDEX IF EXISTS analytics.ix_synth_truth_cell_ts;")
    
    # Revert fm_alarms PK swap
    op.execute("ALTER TABLE raw.fm_alarms DROP CONSTRAINT fm_alarms_pkey;")
    op.execute("ALTER TABLE raw.fm_alarms ADD PRIMARY KEY (alarm_uid);")