"""Resolver for ``recent_cm_change`` triggers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection

from telcoscope.rca.schema import CmChangeTrigger
from telcoscope.rca.triggers.base import MatchResult


def resolve_cm_change(
    incident: dict[str, Any],
    trigger: CmChangeTrigger,
    conn: Connection,
) -> MatchResult | None:
    """Return a match if a recent CM change matches the trigger config.

    Looks for CM changes in ``raw.cm_changes`` within
    ``trigger.cm_change_within_minutes`` *before* ``incident.ts_start``.
    If ``trigger.parameter`` is set, only CM changes to that exact
    parameter name match. Scope:

    - ``same_cell``: ``cm_changes.cell_id = incident.cell_id``
    - ``same_enb``: ``cm_changes.cell_id`` is a sibling of the incident
      cell on the same eNB (requires a join through ``dims.dim_cell``
      because ``raw.cm_changes`` has no eNB id).

    If multiple changes match, the most recent (closest to ``ts_start``)
    wins. Strength decays linearly with temporal distance: 1.0 at
    coincidence, 0.0 at the window edge.
    """
    cell_id: int = incident["cell_id"]
    ts_start: datetime = incident["ts_start"]
    window_delta = timedelta(minutes=trigger.cm_change_within_minutes)

    if trigger.scope == "same_cell":
        cell_filter = "cm.cell_id = %(cell_id)s"
    else:
        # same_enb: cm_changes has no enb_id, so join through dim_cell.
        cell_filter = """
            cm.cell_id IN (
                SELECT c2.cell_id
                FROM dims.dim_cell c1
                JOIN dims.dim_cell c2 ON c2.enb_id = c1.enb_id
                WHERE c1.cell_id = %(cell_id)s
            )
        """

    param_filter = "AND cm.parameter = %(parameter)s" if trigger.parameter else ""

    sql = f"""
        SELECT
            cm.change_uid,
            cm.cell_id,
            cm.parameter,
            cm.old_value,
            cm.new_value,
            cm.changed_at,
            cm.changed_by
        FROM raw.cm_changes cm
        WHERE {cell_filter}
          AND cm.changed_at BETWEEN %(window_start)s AND %(ts_start)s
          {param_filter}
        ORDER BY cm.changed_at DESC
        LIMIT 1
    """

    params: dict[str, Any] = {
        "cell_id": cell_id,
        "window_start": ts_start - window_delta,
        "ts_start": ts_start,
    }
    if trigger.parameter:
        params["parameter"] = trigger.parameter

    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()

    if row is None:
        return None

    (
        change_uid,
        matched_cell_id,
        parameter,
        old_value,
        new_value,
        changed_at,
        changed_by,
    ) = row
    delta_seconds = max((ts_start - changed_at).total_seconds(), 0.0)
    window_seconds = window_delta.total_seconds()
    strength = max(1.0 - delta_seconds / window_seconds, 0.0)

    return MatchResult(
        evidence={
            "change_uid": change_uid,
            "matched_cell_id": matched_cell_id,
            "parameter": parameter,
            "old_value": old_value,
            "new_value": new_value,
            "changed_at": changed_at.isoformat(),
            "changed_by": changed_by,
            "delta_minutes": round(delta_seconds / 60.0, 2),
        },
        strength=round(strength, 4),
    )
