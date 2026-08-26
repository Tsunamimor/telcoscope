"""Anomaly injection patterns for the synthetic data generator.

Each pattern emits a list of (cell_id, ts_start, ts_end, kpi_affected, magnitude)
tuples that the generator then applies to the otherwise-baseline data. The same
list is persisted to a `synth_truth` table so that detection performance can be
evaluated against ground truth.

Pattern types:

- ``sudden_drop``: cliff-edge drop in a single KPI on a single cell (hardware
  fault analogue).
- ``slow_drift``: gradual degradation over hours / days (interference creep,
  ageing component analogue).
- ``correlated_outage``: simultaneous degradation across a cluster of cells
  (transport / backhaul failure analogue).
- ``config_step_change``: instantaneous step in baseline coinciding with a CM
  change (parameter tuning analogue, may not be a real anomaly).
- ``intermittent_spike``: short, repeated spikes in a counter (ping-pong
  handover / CSL analogue).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

PatternType = Literal[
    "sudden_drop",
    "slow_drift",
    "correlated_outage",
    "config_step_change",
    "intermittent_spike",
]


@dataclass
class InjectedAnomaly:
    """A single labelled anomaly to inject into synthetic data.

    Persisted to the truth table for ground-truth evaluation of detectors.
    """

    pattern_type: PatternType
    cell_id: int
    ts_start: datetime
    ts_end: datetime
    kpi_affected: str
    magnitude: float
    description: str = ""


@dataclass
class AnomalyPlan:
    """A plan of all anomalies to inject across the synthetic dataset."""

    anomalies: list[InjectedAnomaly] = field(default_factory=list)

    def add(self, a: InjectedAnomaly) -> None:
        """Append a single anomaly to the plan."""
        self.anomalies.append(a)

    def __len__(self) -> int:
        """Total number of anomalies in the plan."""
        return len(self.anomalies)


def default_anomaly_plan(
    *,
    num_cells: int,
    days: int,
    start: datetime,
    seed: int = 42,
) -> AnomalyPlan:
    """Construct a default anomaly plan over the synthetic dataset.

    Aims for a realistic anomaly rate (~1% of cell-hours affected) with a mix
    of pattern types weighted toward the failure modes detectors most need to
    catch.
    """
    import random

    rng = random.Random(seed)
    plan = AnomalyPlan()

    # Sudden drops: 5 across the dataset, distributed randomly
    for _ in range(5):
        cell_id = rng.randint(1, num_cells)
        day_offset = rng.randint(0, max(0, days - 1))
        hour_offset = rng.randint(0, 23)
        ts_start = start + timedelta(days=day_offset, hours=hour_offset)
        duration_hours = rng.choice([1, 2, 3, 4])
        kpi = rng.choice(["rrc_conn_setup_sr", "erab_drop_rate", "intra_lte_ho_sr"])
        plan.add(
            InjectedAnomaly(
                pattern_type="sudden_drop",
                cell_id=cell_id,
                ts_start=ts_start,
                ts_end=ts_start + timedelta(hours=duration_hours),
                kpi_affected=kpi,
                magnitude=rng.uniform(0.30, 0.60),
                description=f"Sudden {kpi} degradation on cell {cell_id}",
            )
        )

    # Slow drifts: 3, multi-day, more subtle
    for _ in range(3):
        if days < 4:
            # Too short for a meaningful multi-day drift; skip.
            continue
        cell_id = rng.randint(1, num_cells)
        max_start_day = max(0, days - 4)
        day_offset = rng.randint(0, max_start_day)
        ts_start = start + timedelta(days=day_offset)
        # Duration capped so we don't run past the end of the dataset
        duration_days = rng.choice([d for d in [3, 4, 5] if d <= days - day_offset]) \
                        if any(d <= days - day_offset for d in [3, 4, 5]) else 1
        kpi = rng.choice(["dl_user_throughput", "intra_lte_ho_sr"])
        plan.add(
            InjectedAnomaly(
                pattern_type="slow_drift",
                cell_id=cell_id,
                ts_start=ts_start,
                ts_end=ts_start + timedelta(days=duration_days),
                kpi_affected=kpi,
                magnitude=rng.uniform(0.10, 0.25),
                description=f"Slow {kpi} drift on cell {cell_id}",
            )
        )

    # Correlated outage: one event affecting an eNB-sized cluster
    cluster_start_cell = rng.randint(1, max(1, num_cells - 3))
    cluster_cells = list(range(cluster_start_cell, cluster_start_cell + 3))
    day_offset = rng.randint(0, max(0, days - 1))
    ts_start = start + timedelta(days=day_offset, hours=14)
    for cell_id in cluster_cells:
        plan.add(
            InjectedAnomaly(
                pattern_type="correlated_outage",
                cell_id=cell_id,
                ts_start=ts_start,
                ts_end=ts_start + timedelta(hours=2),
                kpi_affected="rrc_conn_setup_sr",
                magnitude=0.80,
                description=f"Transport outage affecting cluster cell {cell_id}",
            )
        )

    return plan
