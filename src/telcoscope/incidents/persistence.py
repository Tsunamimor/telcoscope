"""Upsert incidents into analytics.incidents.

Idempotent on (cell_id, ts_start): rerunning the grouper on the same
anomalies produces the same incidents at the same timestamps, so the
upsert replaces in place rather than duplicating.
"""

from __future__ import annotations

import psycopg
from loguru import logger

from telcoscope.config import settings
from telcoscope.incidents.grouper import Incident

_UPSERT_SQL = """
INSERT INTO analytics.incidents
    (cell_id, ts_start, ts_end, status, severity,
     detection_count, methods, dominant_kpi)
VALUES
    (%(cell_id)s, %(ts_start)s, %(ts_end)s, 'open', %(severity)s,
     %(detection_count)s, %(methods)s, %(dominant_kpi)s)
ON CONFLICT (cell_id, ts_start) DO UPDATE SET
    ts_end          = EXCLUDED.ts_end,
    severity        = EXCLUDED.severity,
    detection_count = EXCLUDED.detection_count,
    methods         = EXCLUDED.methods,
    dominant_kpi    = EXCLUDED.dominant_kpi,
    updated_at      = NOW()
"""


def write_incidents(incidents: list[Incident]) -> int:
    """Upsert a list of Incidents into analytics.incidents.

    Returns the number of rows written (inserted or updated).
    """
    if not incidents:
        logger.info("No incidents to persist")
        return 0

    rows = [
        {
            "cell_id": inc.cell_id,
            "ts_start": inc.ts_start,
            "ts_end": inc.ts_end,
            "severity": inc.severity,
            "detection_count": inc.detection_count,
            "methods": list(inc.methods),  # tuple -> list for psycopg ARRAY
            "dominant_kpi": inc.dominant_kpi,
        }
        for inc in incidents
    ]

    with (
        psycopg.connect(settings.postgres_url.replace("+psycopg", "")) as conn,
        conn.cursor() as cur,
    ):
        cur.executemany(_UPSERT_SQL, rows)

    logger.info("Persisted {} incidents", len(rows))
    return len(rows)
