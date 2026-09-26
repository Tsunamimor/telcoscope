"""Common detector interface and severity mapping.

All detectors implement `detect()` returning a Polars DataFrame with a
consistent schema; a separate `persist()` helper writes to Postgres.
This decoupling means the same detector can be used in batch mode
(evaluate against historical data) or online (append fresh detections
periodically).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl

DETECTION_SCHEMA = {
    "ts": pl.Datetime(time_zone="UTC"),
    "cell_id": pl.Int64,
    "kpi_name": pl.Utf8,
    "score": pl.Float64,
    "severity": pl.Utf8,
    "context": pl.Object,  # dict, serialised to JSONB on persist
}


class Detector(ABC):
    """Abstract base for all anomaly detectors."""

    #: Method name, persisted to `analytics.anomalies.method`.
    method_name: str = "abstract"

    @abstractmethod
    def detect(self, kpis: pl.DataFrame) -> pl.DataFrame:
        """Run detection over the given KPI data.

        Parameters
        ----------
        kpis
            Polars DataFrame with columns matching
            ``mart_kpi_cell_hourly``. Must include ``ts``, ``cell_id``,
            and at least one KPI column.

        Returns:
        -------
        A DataFrame conforming to :data:`DETECTION_SCHEMA`.
        """
        raise NotImplementedError


def score_to_severity(score: float, thresholds: dict[str, float]) -> str:
    """Map a detector's raw score to a severity band.

    Each detector supplies its own thresholds (statistical uses z-score
    magnitudes; isolation forest uses its own decision function scale).
    """
    abs_score = abs(score)
    if abs_score >= thresholds.get("critical", 10.0):
        return "critical"
    if abs_score >= thresholds.get("major", 7.0):
        return "major"
    if abs_score >= thresholds.get("minor", 5.0):
        return "minor"
    return "info"
