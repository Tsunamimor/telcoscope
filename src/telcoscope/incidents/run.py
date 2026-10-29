"""End-to-end: query anomalies → group → upsert incidents → notify new ones."""

from __future__ import annotations

import psycopg
from loguru import logger
from psycopg.rows import dict_row

from telcoscope.config import settings
from telcoscope.incidents.grouper import group_anomalies
from telcoscope.incidents.notifier import notify
from telcoscope.incidents.persistence import write_incidents

_QUERY_ANOMALIES = """
SELECT cell_id, ts, severity, method, kpi_name
FROM analytics.anomalies
WHERE severity != 'info'
ORDER BY cell_id, ts
"""

_QUERY_UNNOTIFIED = """
SELECT incident_id, cell_id, ts_start, ts_end, severity,
       detection_count, methods, dominant_kpi
FROM analytics.incidents
WHERE notified_at IS NULL
ORDER BY ts_start
"""

_MARK_NOTIFIED = """
UPDATE analytics.incidents
   SET notified_at = NOW(),
       updated_at  = NOW()
 WHERE incident_id = %(incident_id)s
"""


def main() -> None:
    dsn = settings.postgres_url.replace("+psycopg", "")

    # 1. Load anomalies, group, upsert incidents
    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(_QUERY_ANOMALIES)
        anomalies = cur.fetchall()
    logger.info("Loaded {} anomalies", len(anomalies))

    incidents = group_anomalies(anomalies)
    compression = len(anomalies) / max(len(incidents), 1)
    logger.info(
        "Grouped {} anomalies into {} incidents ({:.1f}x compression)",
        len(anomalies),
        len(incidents),
        compression,
    )

    written = write_incidents(incidents)
    logger.info("Upserted {} incidents", written)

    # 2. Notify any unnotified incidents (both newly opened and prior retry failures)
    notify_unnotified(dsn)


def notify_unnotified(dsn: str) -> None:
    """Fetch incidents with notified_at IS NULL, notify, then mark."""
    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(_QUERY_UNNOTIFIED)
        pending = cur.fetchall()

        logger.info("Found {} unnotified incidents", len(pending))

        sent = 0
        for incident in pending:
            if notify(incident):
                cur.execute(_MARK_NOTIFIED, {"incident_id": incident["incident_id"]})
                sent += 1

    logger.info("Notification pass done: {} sent, {} skipped", sent, len(pending) - sent)


if __name__ == "__main__":
    main()
