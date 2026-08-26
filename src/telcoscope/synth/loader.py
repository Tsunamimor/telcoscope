"""Bulk load generated synthetic data into Postgres.

Uses `COPY FROM STDIN` for the large fact tables (pm_measurements) and
`executemany` for the small dimension and event tables. On a laptop, loading
~1M PM rows via COPY takes ~15–30 seconds.
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import polars as pl
import psycopg
from loguru import logger

from telcoscope.config import settings

if TYPE_CHECKING:
    from telcoscope.synth.generator import GeneratedData


# Order matters — dimensions before the tables that reference them.
LOAD_ORDER: list[tuple[str, str]] = [
    ("dims.dim_vendor",       "dim_vendor"),
    ("dims.dim_technology",   "dim_technology"),
    ("dims.dim_counter",      "dim_counter"),
    ("dims.dim_enb",          "dim_enb"),
    ("dims.dim_cell",         "dim_cell"),
    ("raw.pm_measurements",   "pm_measurements"),
    ("raw.fm_alarms",         "fm_alarms"),
    ("raw.cm_changes",        "cm_changes"),
    ("analytics.synth_truth", "synth_truth"),
]


def bulk_load(data: "GeneratedData") -> None:
    """Truncate target tables and load all DataFrames from `data`."""
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            # Truncate in reverse dependency order.
            logger.info("Truncating existing data...")
            for table, _ in reversed(LOAD_ORDER):
                cur.execute(f"TRUNCATE TABLE {table} CASCADE;")

            # Load in forward order.
            for table, attr in LOAD_ORDER:
                df: pl.DataFrame = getattr(data, attr)
                if len(df) == 0:
                    logger.warning("{}: empty, skipping", table)
                    continue

                logger.info("Loading {} rows into {}...", len(df), table)
                _copy_dataframe(cur, table, df)

        conn.commit()

    logger.success("Bulk load complete.")


def _copy_dataframe(cur: "psycopg.Cursor", table: str, df: pl.DataFrame) -> None:
    """Stream a Polars DataFrame into Postgres via COPY."""
    columns = df.columns
    col_list = ", ".join(f'"{c}"' for c in columns)

    # Write to an in-memory CSV buffer, then COPY from that buffer.
    buf = io.StringIO()
    df.write_csv(buf, include_header=False, datetime_format="%Y-%m-%d %H:%M:%S%z")
    buf.seek(0)

    with cur.copy(
        f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"
    ) as copy:
        while chunk := buf.read(64 * 1024):
            copy.write(chunk)