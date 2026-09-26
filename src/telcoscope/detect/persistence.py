"""Persist detections from any detector to analytics.anomalies."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import polars as pl
import psycopg
from loguru import logger

from telcoscope.config import settings


def persist_detections(detections: pl.DataFrame, method: str) -> int:
    """Insert detection rows into analytics.anomalies.

    Returns the number of rows written.
    """
    if len(detections) == 0:
        logger.info("No detections to persist")
        return 0

    detected_at = datetime.now(UTC)

    # Strip SQLAlchemy driver suffix for raw psycopg
    conn_str = settings.postgres_url.replace("+psycopg", "")

    rows_inserted = 0
    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        for row in detections.iter_rows(named=True):
            context = row.get("context")
            if isinstance(context, dict):
                context_json = json.dumps(context)
            elif context is None:
                context_json = json.dumps({})
            else:
                context_json = json.dumps(context)

            cur.execute(
                """
                    INSERT INTO analytics.anomalies (
                        ts, cell_id, kpi_name, method, score, severity,
                        context, detected_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                (
                    row["ts"],
                    row["cell_id"],
                    row["kpi_name"],
                    method,
                    row["score"],
                    row["severity"],
                    context_json,
                    detected_at,
                ),
            )
            rows_inserted += 1
        conn.commit()

    logger.info("Persisted {} detections (method={})", rows_inserted, method)
    return rows_inserted
