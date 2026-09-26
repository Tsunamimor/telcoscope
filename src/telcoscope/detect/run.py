"""Run one or more detectors against the current KPI marts."""

from __future__ import annotations

import polars as pl
import psycopg
from loguru import logger

from telcoscope.config import settings
from telcoscope.detect.persistence import persist_detections
from telcoscope.detect.statistical import StatisticalDetector


def load_mart_kpi_cell_hourly() -> pl.DataFrame:
    """Read the KPI mart into a Polars DataFrame."""
    with psycopg.connect(settings.postgres_url) as conn:
        return pl.read_database(
            "SELECT * FROM dbt_dev_marts.mart_kpi_cell_hourly ORDER BY ts, cell_id",
            connection=conn,
        )


def run_statistical() -> int:
    """Run the statistical detector end-to-end."""
    logger.info("Loading KPI mart")
    kpis = load_mart_kpi_cell_hourly()
    logger.info("Loaded {} rows", len(kpis))

    detector = StatisticalDetector(lookback_weeks=4)
    detections = detector.detect(kpis)

    return persist_detections(detections, method=detector.method_name)


if __name__ == "__main__":
    n = run_statistical()
    logger.info("Done — {} rows written to analytics.anomalies", n)
