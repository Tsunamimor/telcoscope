"""Resolver for ``concurrent_fm_alarm`` triggers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection

from telcoscope.rca.schema import AlarmTrigger
from telcoscope.rca.triggers.base import MatchResult

# Severity ordering so we can filter by minimum severity in SQL.
# Keys mirror the ``Severity`` Literal in ``rca.schema``.
_SEVERITY_RANK = {
    "warning": 1,
    "minor": 2,
    "major": 3,
    "critical": 4,
}


def resolve_alarm(
    incident: dict[str, Any],
    trigger: AlarmTrigger,
    conn: Connection,
) -> MatchResult | None:
    """Return a match if a concurrent FM alarm matches the trigger config.

    Looks for FM alarms in ``raw.fm_alarms`` raised within
    ``trigger.within_minutes`` *before* ``incident.ts_start``, matching
    ``trigger.alarm_pattern`` as a POSIX regex against ``alarm_type``,
    at or above ``trigger.severity_min``. The scope filter picks which
    cells count:

    - ``same_cell``: ``fm_alarms.cell_id = incident.cell_id``
    - ``same_enb``: ``fm_alarms.enb_id`` equals the incident cell's eNB
    - ``same_region``: v1 proxy — treated as ``same_enb`` (no region
      dimension in the schema yet)

    If multiple alarms match, the one closest in time to ``ts_start``
    wins. Strength decays linearly with temporal distance: 1.0 at
    coincidence, 0.0 at the window edge.
    """
    cell_id: int = incident["cell_id"]
    ts_start: datetime = incident["ts_start"]
    severity_floor = _SEVERITY_RANK[trigger.severity_min]
    window_delta = timedelta(minutes=trigger.within_minutes)

    if trigger.scope == "same_cell":
        cell_filter = "f.cell_id = %(cell_id)s"
    else:
        # same_enb / same_region: match on sibling cells of the same eNB.
        # fm_alarms has its own enb_id column (NOT NULL), so no join
        # through dim_cell is required.
        cell_filter = """
            f.enb_id = (
                SELECT enb_id FROM dims.dim_cell WHERE cell_id = %(cell_id)s
            )
        """

    sql = f"""
        SELECT
            f.alarm_uid,
            f.cell_id,
            f.enb_id,
            f.alarm_type,
            f.severity,
            f.raised_at
        FROM raw.fm_alarms f
        WHERE {cell_filter}
          AND f.raised_at BETWEEN %(window_start)s AND %(ts_start)s
          AND f.alarm_type ~ %(pattern)s
          AND CASE f.severity
                WHEN 'warning' THEN 1
                WHEN 'minor' THEN 2
                WHEN 'major' THEN 3
                WHEN 'critical' THEN 4
                ELSE 0
              END >= %(severity_floor)s
        ORDER BY ABS(EXTRACT(EPOCH FROM (%(ts_start)s - f.raised_at)))
        LIMIT 1
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "cell_id": cell_id,
                "window_start": ts_start - window_delta,
                "ts_start": ts_start,
                "pattern": trigger.alarm_pattern,
                "severity_floor": severity_floor,
            },
        )
        row = cur.fetchone()

    if row is None:
        return None

    alarm_uid, matched_cell_id, enb_id, alarm_type, severity, raised_at = row
    delta_seconds = max((ts_start - raised_at).total_seconds(), 0.0)
    window_seconds = window_delta.total_seconds()
    strength = max(1.0 - delta_seconds / window_seconds, 0.0)

    return MatchResult(
        evidence={
            "alarm_uid": alarm_uid,
            "matched_cell_id": matched_cell_id,
            "enb_id": enb_id,
            "alarm_type": alarm_type,
            "severity": severity,
            "raised_at": raised_at.isoformat(),
            "delta_minutes": round(delta_seconds / 60.0, 2),
        },
        strength=round(strength, 4),
    )
