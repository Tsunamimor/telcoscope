"""Statistical anomaly detector using seasonal modified z-score.

For each (cell, KPI) combination, score every point against a rolling
window of same-hour-of-week values from the previous N weeks.
"""

from __future__ import annotations

import polars as pl
from loguru import logger

from telcoscope.detect.base import DETECTION_SCHEMA, Detector, score_to_severity

# Modified z-score constant — Iglewicz-Hoaglin
_MZS_CONST = 0.6745

# KPIs to score (one detector, all KPIs — filtered downstream if needed)
_KPIS_TO_SCORE = [
    "rrc_conn_setup_sr",
    "erab_setup_sr",
    "erab_drop_rate",
    "intra_lte_ho_sr",
    "dl_user_throughput_kbps",
    "cell_availability_pct",
]

# Threshold bands for severity
_SEVERITY_THRESHOLDS = {
    "minor": 3.5,
    "major": 7.0,
    "critical": 10.0,
}


class StatisticalDetector(Detector):
    """Seasonal modified-z-score detector.

    Parameters
    ----------
    lookback_weeks
        How many weeks of same-hour-of-week history to score against.
        4 is a reasonable default: enough data for stable estimates,
        recent enough to reflect the current network state.
    kpis
        Which KPI columns to score. Defaults to all six 3GPP KPIs.
    """

    method_name = "statistical"

    def __init__(
        self,
        lookback_weeks: int = 4,
        kpis: list[str] | None = None,
    ) -> None:
        self.lookback_weeks = lookback_weeks
        self.kpis = kpis or _KPIS_TO_SCORE

    def detect(self, kpis: pl.DataFrame) -> pl.DataFrame:
        """Score every (ts, cell, kpi) triple against its seasonal baseline."""
        logger.info(
            "Statistical detector: scoring {} rows across {} cells",
            len(kpis),
            kpis["cell_id"].n_unique(),
        )

        # Add day-of-week + hour-of-day columns for the seasonal grouping
        scored = kpis.with_columns(
            pl.col("ts").dt.weekday().alias("_dow"),
            pl.col("ts").dt.hour().alias("_hod"),
        )

        detections: list[pl.DataFrame] = []

        for kpi in self.kpis:
            if kpi not in scored.columns:
                logger.warning("KPI {} not in dataframe — skipping", kpi)
                continue

            # For each (cell, dow, hod) group, compute median and MAD
            baselines = scored.group_by(["cell_id", "_dow", "_hod"]).agg(
                pl.col(kpi).median().alias("_median"),
                (pl.col(kpi) - pl.col(kpi).median()).abs().median().alias("_mad"),
            )

            # Join baselines back onto the raw data
            enriched = scored.join(baselines, on=["cell_id", "_dow", "_hod"], how="left")

            # Compute modified z-score
            enriched = enriched.with_columns(
                pl.when(pl.col("_mad") > 0)
                .then(_MZS_CONST * (pl.col(kpi) - pl.col("_median")) / pl.col("_mad"))
                .otherwise(0.0)
                .alias("_z")
            )

            # Filter to outliers only
            outliers = enriched.filter(pl.col("_z").abs() >= 3.5)

            if len(outliers) == 0:
                continue

            # Map to the detection schema
            method_detections = outliers.with_columns(
                pl.lit(kpi).alias("kpi_name"),
                pl.col("_z").alias("score"),
                pl.col("_z")
                .map_elements(
                    lambda z: score_to_severity(z, _SEVERITY_THRESHOLDS),
                    return_dtype=pl.Utf8,
                )
                .alias("severity"),
                pl.struct(
                    [
                        pl.col("_median").alias("baseline_median"),
                        pl.col("_mad").alias("baseline_mad"),
                        pl.col(kpi).alias("observed_value"),
                    ]
                ).alias("context"),
            ).select(["ts", "cell_id", "kpi_name", "score", "severity", "context"])

            detections.append(method_detections)

        if not detections:
            logger.info("No outliers found across any KPI")
            return pl.DataFrame(schema=DETECTION_SCHEMA)      # type: ignore[arg-type]

        result = pl.concat(detections)
        logger.info("Statistical detector: {} outliers found", len(result))
        return result
