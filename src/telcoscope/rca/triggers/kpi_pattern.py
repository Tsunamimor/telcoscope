"""Resolver for ``kpi_pattern`` triggers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection

from telcoscope.rca.schema import KpiPatternTrigger
from telcoscope.rca.triggers.base import MatchResult

# Columns we trust in dbt_dev_marts.mart_kpi_cell_hourly. Anything
# outside this allow-list is rejected before the SQL is built so the
# trigger.kpi string cannot be used for SQL injection.
_ALLOWED_KPIS: frozenset[str] = frozenset(
    {
        "rrc_conn_setup_sr",
        "erab_setup_sr",
        "erab_drop_rate",
        "intra_lte_ho_sr",
        "dl_user_throughput_kbps",
        "cell_availability_pct",
    }
)


def resolve_kpi_pattern(
    incident: dict[str, Any],
    trigger: KpiPatternTrigger,
    conn: Connection,
) -> MatchResult | None:
    """Return a match if the named KPI shows the expected drop or spike.

    Compares the KPI value in ``dbt_dev_marts.mart_kpi_cell_hourly`` at
    the hour of ``incident.ts_start`` against the baseline from the 24h
    to 1h window before ``ts_start`` on the same cell (the same
    convention used in ``mart_incidents_timeline``). Fires only when
    ``|pct_change|`` meets ``trigger.magnitude_pct`` *in the direction*
    set by ``trigger.direction``:

    - ``drop`` -> fires on negative change
    - ``spike`` -> fires on positive change

    Strength is the magnitude ratio clipped at 1.0: matching at exactly
    the threshold gives strength 1.0 only when magnitude == threshold;
    for larger magnitudes it saturates. Returns None when the KPI value
    is missing, the baseline is empty or zero, the direction mismatches,
    or the magnitude is below threshold.

    Only ``scope == "same_cell"`` is meaningful for a KPI pattern — the
    mart is keyed on ``(ts, cell_id)``. Other scope values are accepted
    by the pydantic schema but ignored here.
    """
    if trigger.kpi not in _ALLOWED_KPIS:
        raise ValueError(f"Unknown KPI name {trigger.kpi!r}; allowed: {sorted(_ALLOWED_KPIS)}")

    cell_id: int = incident["cell_id"]
    ts_start: datetime = incident["ts_start"]
    hour = ts_start.replace(minute=0, second=0, microsecond=0)

    # trigger.kpi is validated against _ALLOWED_KPIS above so inlining it
    # into the SQL is safe. The actual values flow through parameters.
    sql = f"""
        WITH current_val AS (
            SELECT {trigger.kpi} AS val
            FROM dbt_dev_marts.mart_kpi_cell_hourly
            WHERE cell_id = %(cell_id)s
              AND ts = %(hour)s
        ),
        baseline AS (
            SELECT AVG({trigger.kpi}) AS val
            FROM dbt_dev_marts.mart_kpi_cell_hourly
            WHERE cell_id = %(cell_id)s
              AND ts BETWEEN %(baseline_start)s AND %(baseline_end)s
        )
        SELECT current_val.val, baseline.val FROM current_val, baseline
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "cell_id": cell_id,
                "hour": hour,
                "baseline_start": hour - timedelta(hours=24),
                "baseline_end": hour - timedelta(hours=1),
            },
        )
        row = cur.fetchone()

    if row is None:
        return None

    current_val, baseline_val = row
    if current_val is None or baseline_val is None or baseline_val == 0:
        return None

    pct_change = (float(current_val) - float(baseline_val)) / float(baseline_val) * 100.0

    direction_matches = (trigger.direction == "drop" and pct_change < 0) or (
        trigger.direction == "spike" and pct_change > 0
    )
    if not direction_matches:
        return None

    magnitude = abs(pct_change)
    if magnitude < trigger.magnitude_pct:
        return None

    strength = min(magnitude / trigger.magnitude_pct, 1.0)

    return MatchResult(
        evidence={
            "kpi": trigger.kpi,
            "direction": trigger.direction,
            "current_value": round(float(current_val), 4),
            "baseline_value": round(float(baseline_val), 4),
            "pct_change": round(pct_change, 2),
            "threshold_pct": trigger.magnitude_pct,
        },
        strength=round(strength, 4),
    )
