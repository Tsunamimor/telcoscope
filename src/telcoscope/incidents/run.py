"""End-to-end: query anomalies → group → upsert incidents."""
from __future__ import annotations

import psycopg
from loguru import logger
from psycopg.rows import dict_row

from telcoscope.config import settings
from telcoscope.incidents.grouper import group_anomalies
from telcoscope.incidents.persistence import write_incidents

_QUERY_ANOMALIES = """
SELECT cell_id, ts, severity, method, kpi_name
FROM analytics.anomalies
WHERE severity != 'info'
ORDER BY cell_id, ts
"""


def main() -> None:
    dsn = settings.postgres_url.replace("+psycopg", "")

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
    logger.info("Done: {} incidents written", written)


if __name__ == "__main__":
    main()