"""Incident grouping: collapse raw detections into time-bounded incidents.

Pure functions, no I/O. See docs/decisions/DEC-004-incidents.md for the
grouping model (cell_id + 2h silence threshold, max-severity rollup).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

GAP_THRESHOLD = timedelta(hours=2)

_SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}
_RANK_TO_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}


@dataclass(frozen=True)
class Incident:
    cell_id: str
    ts_start: datetime
    ts_end: datetime
    severity: str
    detection_count: int
    methods: tuple[str, ...]
    dominant_kpi: str | None


def group_anomalies(anomalies: list[dict]) -> list[Incident]:
    """Collapse a list of anomaly dicts into incidents.

    Each anomaly dict must have: cell_id, ts, severity, method, kpi_name.
    Incidents are formed by walking anomalies sorted by (cell_id, ts) and
    starting a new group whenever the cell changes or the gap exceeds
    GAP_THRESHOLD.
    """
    if not anomalies:
        return []

    sorted_anoms = sorted(anomalies, key=lambda a: (a["cell_id"], a["ts"]))

    incidents: list[Incident] = []
    current: list[dict] = [sorted_anoms[0]]

    for anom in sorted_anoms[1:]:
        last = current[-1]
        same_cell = anom["cell_id"] == last["cell_id"]
        within_gap = (anom["ts"] - last["ts"]) <= GAP_THRESHOLD

        if same_cell and within_gap:
            current.append(anom)
        else:
            incidents.append(_group_to_incident(current))
            current = [anom]

    incidents.append(_group_to_incident(current))
    return incidents


def _group_to_incident(group: list[dict]) -> Incident:
    max_rank = max(_SEVERITY_RANK.get(a["severity"], 0) for a in group)
    methods = tuple(sorted({a["method"] for a in group}))
    kpi_counts = Counter(a["kpi_name"] for a in group if a.get("kpi_name"))
    dominant_kpi = kpi_counts.most_common(1)[0][0] if kpi_counts else None

    return Incident(
        cell_id=group[0]["cell_id"],
        ts_start=min(a["ts"] for a in group),
        ts_end=max(a["ts"] for a in group),
        severity=_RANK_TO_SEVERITY[max_rank],
        detection_count=len(group),
        methods=methods,
        dominant_kpi=dominant_kpi,
    )