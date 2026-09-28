"""Run all configured detectors against the current KPI marts."""
from __future__ import annotations

import polars as pl
import psycopg
from loguru import logger

from telcoscope.config import settings
from telcoscope.detect.isolation import IsolationForestDetector
from telcoscope.detect.persistence import persist_detections
from telcoscope.detect.statistical import StatisticalDetector


def load_mart_kpi_cell_hourly() -> pl.DataFrame:
    """Read the KPI mart into a Polars DataFrame."""
    with psycopg.connect(settings.postgres_url.replace("+psycopg", "")) as conn:
        return pl.read_database(
            "SELECT * FROM dbt_dev_marts.mart_kpi_cell_hourly ORDER BY ts, cell_id",
            connection=conn,
        )


def run_all_detectors() -> dict[str, int]:
    """Run every configured detector; return {method: rows_persisted}."""
    logger.info("Loading KPI mart")
    kpis = load_mart_kpi_cell_hourly()
    logger.info("Loaded {} rows", len(kpis))

    results = {}

    # Statistical (fast, ~3s)
    stat_detector = StatisticalDetector(lookback_weeks=4)
    stat_detections = stat_detector.detect(kpis)
    results[stat_detector.method_name] = persist_detections(
        stat_detections, method=stat_detector.method_name
    )

    # Isolation Forest (slower, ~10s)
    if_detector = IsolationForestDetector(
        contamination=0.02, n_estimators=200
    )
    if_detections = if_detector.detect(kpis)
    results[if_detector.method_name] = persist_detections(
        if_detections, method=if_detector.method_name
    )

    return results


if __name__ == "__main__":
    results = run_all_detectors()
    for method, count in results.items():
        logger.info("Method {}: {} anomalies persisted", method, count)