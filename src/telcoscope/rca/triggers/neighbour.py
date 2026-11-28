"""Resolver for ``neighbour_cell_anomaly`` triggers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection

from telcoscope.rca.schema import NeighbourAnomalyTrigger
from telcoscope.rca.triggers.base import MatchResult


def resolve_neighbour(
    incident: dict[str, Any],
    trigger: NeighbourAnomalyTrigger,
    conn: Connection,
) -> MatchResult | None:
    """Return a match if enough neighbour cells are also anomalous.

    Counts distinct cells with anomalies in ``analytics.anomalies``
    within ``trigger.within_minutes`` on either side of
    ``incident.ts_start``, among cells sharing the same eNB as the
    incident cell (v1 proxy for a true neighbour graph — see DEC-006
    §3). Excludes the incident's own cell from the count.

    Fires when the distinct neighbour count reaches
    ``trigger.neighbour_anomalies_min``. Strength scales above threshold:

    - count == threshold -> 0.5
    - count == 2× threshold -> 1.0 (saturated)
    - count below threshold -> no match (returns None)
    """
    cell_id: int = incident["cell_id"]
    ts_start: datetime = incident["ts_start"]
    window = timedelta(minutes=trigger.within_minutes)

    sql = """
        WITH neighbour_cells AS (
            SELECT c2.cell_id
            FROM dims.dim_cell c1
            JOIN dims.dim_cell c2 ON c2.enb_id = c1.enb_id
            WHERE c1.cell_id = %(cell_id)s
              AND c2.cell_id <> %(cell_id)s
        )
        SELECT
            COUNT(DISTINCT a.cell_id)                 AS matched_cells,
            COALESCE(ARRAY_AGG(DISTINCT a.cell_id), ARRAY[]::bigint[])
                                                       AS cell_ids
        FROM analytics.anomalies a
        JOIN neighbour_cells n ON n.cell_id = a.cell_id
        WHERE a.ts BETWEEN %(window_start)s AND %(window_end)s
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "cell_id": cell_id,
                "window_start": ts_start - window,
                "window_end": ts_start + window,
            },
        )
        row = cur.fetchone()

    if row is None:
        return None

    matched_cells, cell_ids = row
    matched_cells = matched_cells or 0
    threshold = trigger.neighbour_anomalies_min

    if matched_cells < threshold:
        return None

    # Linear ramp above threshold: 0.5 at threshold, 1.0 at 2× threshold.
    ratio = matched_cells / threshold
    strength = min(0.5 + 0.5 * (ratio - 1), 1.0)
    strength = max(strength, 0.5)

    return MatchResult(
        evidence={
            "neighbour_cell_count": matched_cells,
            "neighbour_cell_ids": list(cell_ids) if cell_ids else [],
            "threshold": threshold,
            "window_minutes": trigger.within_minutes,
        },
        strength=round(strength, 4),
    )
