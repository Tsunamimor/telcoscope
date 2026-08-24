"""Synthetic PM/FM/CM data generator.

Produces realistic-looking hourly counter data across a configurable number of
LTE cells, with diurnal + weekly seasonality and a labelled set of injected
anomalies for ground-truth evaluation.

Entry point: ``generate_and_load()`` — generates the data in memory and writes
it to the configured Postgres instance.

This is the v1 skeleton. The full implementation is filled in during Week 1.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from loguru import logger

from telcoscope.config import settings
from telcoscope.synth.anomalies import default_anomaly_plan
from telcoscope.synth.archetypes import ARCHETYPES, archetype_distribution

if TYPE_CHECKING:
    import polars as pl


def generate_and_load(
    *,
    num_cells: int | None = None,
    num_days: int | None = None,
    seed: int | None = None,
) -> None:
    """Generate synthetic data and load it into Postgres.

    Parameters
    ----------
    num_cells:
        How many cells to model. Defaults to ``settings.synth_num_cells``.
    num_days:
        How many days of data to generate. Defaults to ``settings.synth_days``.
    seed:
        Random seed for reproducibility. Defaults to ``settings.synth_seed``.
    """
    cells = num_cells or settings.synth_num_cells
    days = num_days or settings.synth_days
    rng_seed = seed if seed is not None else settings.synth_seed

    logger.info(
        "Synthetic generator: cells={} days={} seed={}",
        cells, days, rng_seed,
    )

    start = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=days)

    # 1) Generate dimension data (cells, eNBs, vendors, counters)
    logger.info("Generating dimension data...")
    # TODO (Week 1): emit dim_cell, dim_enb, dim_vendor, dim_technology

    # 2) Plan anomalies (ground truth)
    plan = default_anomaly_plan(
        num_cells=cells, days=days, start=start, seed=rng_seed
    )
    logger.info("Planned {} injected anomalies", len(plan))

    # 3) Generate baseline PM counters with diurnal + weekly seasonality
    logger.info("Generating baseline PM counters...")
    # TODO (Week 1): per-cell-per-hour counter rows respecting archetype mix
    _ = ARCHETYPES, archetype_distribution

    # 4) Overlay anomalies onto baseline
    logger.info("Overlaying anomalies onto baseline...")
    # TODO (Week 1): apply each InjectedAnomaly to the matching cell-hours

    # 5) Generate FM alarms (some real, some red herrings)
    logger.info("Generating FM alarms...")
    # TODO (Week 1)

    # 6) Generate CM changes
    logger.info("Generating CM changes...")
    # TODO (Week 1)

    # 7) Bulk-load into Postgres
    logger.info("Bulk-loading into Postgres at {}", settings.postgres_host)
    # TODO (Week 1): COPY-based bulk load via psycopg

    logger.success("Synthetic data generation complete.")


def _build_cell_population(num_cells: int, rng_seed: int) -> "pl.DataFrame":
    """Build the dim_cell rows respecting archetype distribution.

    Not yet implemented — placeholder so the import path exists.
    """
    raise NotImplementedError("Implemented in Week 1")


if __name__ == "__main__":
    generate_and_load()
