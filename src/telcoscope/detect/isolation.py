"""Isolation Forest anomaly detector.

Multivariate — considers all six KPIs jointly per (cell, hour) row.
Uses scikit-learn's IsolationForest with hyperparameters tuned for
telecoms KPI data (many rows per cell, seasonal, mostly-clean).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl
from loguru import logger
from sklearn.ensemble import IsolationForest

from telcoscope.detect.base import DETECTION_SCHEMA, Detector, score_to_severity

_FEATURE_COLS = [
    "rrc_conn_setup_sr",
    "erab_setup_sr",
    "erab_drop_rate",
    "intra_lte_ho_sr",
    "dl_user_throughput_kbps",
    "cell_availability_pct",
]

# For IF, we invert scores so that positive = more anomalous, matching
# the statistical detector's convention. sklearn's decision_function
# returns positive for normal, negative for anomalous — we flip.
_SEVERITY_THRESHOLDS = {
    "minor": 0.05,
    "major": 0.15,
    "critical": 0.30,
}


class IsolationForestDetector(Detector):
    """Isolation Forest applied to the KPI marts, one model per cell type."""

    method_name = "isolation_forest"

    def __init__(
        self,
        contamination: float = 0.02,
        n_estimators: int = 200,
        random_state: int = 42,
    ) -> None:
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state

    def detect(self, kpis: pl.DataFrame) -> pl.DataFrame:
        """Fit a global model, then score every point."""
        logger.info("IF detector: preparing features from {} rows", len(kpis))

        # Filter out rows where any feature is null — IF can't handle NaN
        clean = kpis.drop_nulls(subset=_FEATURE_COLS)
         # Cast Decimal -> Float64 so median() and downstream ops behave
        clean = clean.with_columns(
            [pl.col(c).cast(pl.Float64) for c in _FEATURE_COLS]
        )
        logger.info(
            "Dropped {} rows with null KPIs, {} remaining",
            len(kpis) - len(clean),
            len(clean),
        )

        X = clean.select(_FEATURE_COLS).to_numpy()

        logger.info(
            "Fitting IsolationForest: n_estimators={}, contamination={}",
            self.n_estimators,
            self.contamination,
        )
        model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,      # use all cores
        )
        model.fit(X)

        # decision_function: positive = normal, negative = anomalous
        # We invert so positive = anomalous, matching statistical convention
        raw_scores = -model.decision_function(X)
        predictions = model.predict(X)      # 1 = normal, -1 = anomalous

        # Filter to only the anomalous predictions
        anomalous_mask = predictions == -1

        if not anomalous_mask.any():
            logger.info("IF detector: no anomalies found")
            return pl.DataFrame(schema=DETECTION_SCHEMA)

        anomalous = clean.filter(
            pl.Series(anomalous_mask)
        ).with_columns(
            pl.Series("_score", raw_scores[anomalous_mask]),
        )

        # For multivariate detectors, kpi_name records which KPI most
        # contributed. Cheap heuristic: the KPI most abnormal (largest
        # |value - column median|) at that row.
        column_medians = clean.select(_FEATURE_COLS).median().row(0)

        def dominant_kpi(row: dict) -> str:
            distances = {}
            for i, col in enumerate(_FEATURE_COLS):
                val = row.get(col)
                med = column_medians[i]
                if val is None or med is None:
                    distances[col] = 0.0
                else:
                    distances[col] = abs(float(val) - float(med))
            return max(distances, key=distances.get)

        detections = anomalous.with_columns(
            pl.struct(_FEATURE_COLS).map_elements(
                dominant_kpi, return_dtype=pl.Utf8
            ).alias("kpi_name"),
            pl.col("_score").alias("score"),
            pl.col("_score").map_elements(
                lambda s: score_to_severity(s, _SEVERITY_THRESHOLDS),
                return_dtype=pl.Utf8,
            ).alias("severity"),
        )

        # Assemble context — record all six KPI values
        detections = detections.with_columns(
            pl.struct(_FEATURE_COLS).alias("context"),
        )

        result = detections.select(
            ["ts", "cell_id", "kpi_name", "score", "severity", "context"]
        )
        logger.info("IF detector: {} anomalies flagged", len(result))
        return result