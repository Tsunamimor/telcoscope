"""Synthetic PM/FM/CM data generator for telcoscope.

Produces realistic hourly counter data across a population of LTE cells with
diurnal + weekly seasonality per archetype, and overlays a labelled set of
anomalies for ground-truth detector evaluation.

Entry point: `generate_and_load()`.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
from loguru import logger

from telcoscope.config import settings
from telcoscope.synth.anomalies import AnomalyPlan, default_anomaly_plan
from telcoscope.synth.archetypes import (
    ARCHETYPES,
    Archetype,
    ArchetypeName,
    archetype_distribution,
)
from telcoscope.synth.timeseries import (
    diurnal_factor,
    hourly_range,
    noise,
    weekly_factor,
)

# Counter IDs must match dbt/seeds/counter_catalog.csv exactly.
COUNTERS = {
    "RRC_CONN_SETUP_ATT":     1,
    "RRC_CONN_SETUP_SUCC":    2,
    "ERAB_ESTAB_ATT_INIT":    3,
    "ERAB_ESTAB_SUCC_INIT":   4,
    "ERAB_ESTAB_ATT_ADDED":   5,
    "ERAB_ESTAB_SUCC_ADDED":  6,
    "ERAB_REL_NORMAL_ENB":    7,
    "ERAB_REL_ABNORMAL_ENB":  8,
    "HO_EXEC_ATT_INTRA_LTE":  9,
    "HO_EXEC_SUCC_INTRA_LTE": 10,
    "PDCP_VOL_DL_DRB":        11,
    "UE_THP_TIME_DL":         12,
    "CELL_DOWNTIME_AUTO":     13,
    "CELL_DOWNTIME_MAN":      14,
}


@dataclass
class GeneratedData:
    """Container for all data produced by one generator run."""

    dim_vendor: pl.DataFrame
    dim_technology: pl.DataFrame
    dim_counter: pl.DataFrame
    dim_enb: pl.DataFrame
    dim_cell: pl.DataFrame
    pm_measurements: pl.DataFrame
    fm_alarms: pl.DataFrame
    cm_changes: pl.DataFrame
    synth_truth: pl.DataFrame


def generate(
    *,
    num_cells: int = 100,
    num_days: int = 30,
    seed: int = 42,
    start: datetime | None = None,
) -> GeneratedData:
    """Generate a complete synthetic dataset in memory.

    Parameters
    ----------
    num_cells:
        Number of cells to model.
    num_days:
        Number of days of history to generate.
    seed:
        Random seed for reproducibility.
    start:
        Start timestamp (UTC). Defaults to `now` rounded down to midnight,
        minus `num_days`.
    """
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)

    if start is None:
        start = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=num_days)

    logger.info(
        "Generating: {} cells × {} days from {} (seed={})",
        num_cells, num_days, start, seed,
    )

    # 1. Dimensions
    dim_vendor = _build_dim_vendor()
    dim_tech = _build_dim_technology()
    dim_counter = _build_dim_counter(dim_vendor, dim_tech)
    dim_enb, dim_cell = _build_network(num_cells, start, py_rng)

    # 2. Anomaly plan (ground truth)
    plan = default_anomaly_plan(
        num_cells=num_cells, days=num_days, start=start, seed=seed
    )
    logger.info("Planned {} anomalies", len(plan))

    # 3. Baseline PM counters
    pm = _generate_pm_measurements(
        dim_cell=dim_cell,
        start=start,
        num_days=num_days,
        rng=rng,
    )

    # 4. Overlay anomalies onto PM
    pm = _apply_anomalies(pm, plan)

    # 5. FM alarms — some correlated with anomalies, some background noise
    fm = _generate_fm_alarms(dim_cell, plan, start, num_days, py_rng)

    # 6. CM changes — sparse, occasional parameter tweaks
    cm = _generate_cm_changes(dim_cell, start, num_days, py_rng)

    # 7. Truth table
    truth = pl.DataFrame(
        [
            {
                "pattern_type": a.pattern_type,
                "cell_id": a.cell_id,
                "ts_start": a.ts_start,
                "ts_end": a.ts_end,
                "kpi_affected": a.kpi_affected,
                "magnitude": a.magnitude,
                "description": a.description,
            }
            for a in plan.anomalies
        ]
    )

    return GeneratedData(
        dim_vendor=dim_vendor,
        dim_technology=dim_tech,
        dim_counter=dim_counter,
        dim_enb=dim_enb,
        dim_cell=dim_cell,
        pm_measurements=pm,
        fm_alarms=fm,
        cm_changes=cm,
        synth_truth=truth,
    )


# --- Dimension builders ----------------------------------------------------

def _build_dim_vendor() -> pl.DataFrame:
    return pl.DataFrame({"vendor_id": [1], "vendor_name": ["synth_vendor_a"]})


def _build_dim_technology() -> pl.DataFrame:
    return pl.DataFrame({
        "technology_id": [1, 2, 3],
        "technology": ["LTE", "5G_NSA", "5G_SA"],
        "release": ["Rel-14", "Rel-15", "Rel-16"],
    })


def _build_dim_counter(vendor: pl.DataFrame, tech: pl.DataFrame) -> pl.DataFrame:
    """One row per logical counter, matching the CSV seed."""
    rows = [
        (1,  "RRC_CONN_SETUP_ATT",     "accessibility", "count"),
        (2,  "RRC_CONN_SETUP_SUCC",    "accessibility", "count"),
        (3,  "ERAB_ESTAB_ATT_INIT",    "accessibility", "count"),
        (4,  "ERAB_ESTAB_SUCC_INIT",   "accessibility", "count"),
        (5,  "ERAB_ESTAB_ATT_ADDED",   "accessibility", "count"),
        (6,  "ERAB_ESTAB_SUCC_ADDED",  "accessibility", "count"),
        (7,  "ERAB_REL_NORMAL_ENB",    "retainability", "count"),
        (8,  "ERAB_REL_ABNORMAL_ENB",  "retainability", "count"),
        (9,  "HO_EXEC_ATT_INTRA_LTE",  "mobility",      "count"),
        (10, "HO_EXEC_SUCC_INTRA_LTE", "mobility",      "count"),
        (11, "PDCP_VOL_DL_DRB",        "integrity",     "kbits"),
        (12, "UE_THP_TIME_DL",         "integrity",     "seconds"),
        (13, "CELL_DOWNTIME_AUTO",     "availability",  "seconds"),
        (14, "CELL_DOWNTIME_MAN",      "availability",  "seconds"),
    ]
    return pl.DataFrame({
        "counter_id":         [r[0] for r in rows],
        "name":               [r[1] for r in rows],
        "description":        [r[1].replace("_", " ").lower() for r in rows],
        "kpi_group":          [r[2] for r in rows],
        "vendor_id":          [1] * len(rows),
        "vendor_counter_name": [f"vendor_a::{r[1]}" for r in rows],
        "technology_id":      [1] * len(rows),
        "unit":               [r[3] for r in rows],
    })


def _build_network(
    num_cells: int, now: datetime, rng: random.Random
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build eNB and cell populations respecting archetype distribution."""
    dist = archetype_distribution()
    archetype_names: list[ArchetypeName] = []
    for name, share in dist.items():
        archetype_names.extend([name] * round(num_cells * share))
    # Pad/truncate to exactly num_cells
    while len(archetype_names) < num_cells:
        archetype_names.append("suburban")
    archetype_names = archetype_names[:num_cells]
    rng.shuffle(archetype_names)

    # eNBs: roughly one per 3 cells (3-sector sites)
    num_enbs = max(1, num_cells // 3)
    dim_enb = pl.DataFrame({
        "enb_id":    list(range(1, num_enbs + 1)),
        "enb_name":  [f"eNB_{i:05d}" for i in range(1, num_enbs + 1)],
        "vendor_id": [1] * num_enbs,
        "region":    [rng.choice(["north", "south", "east", "west"]) for _ in range(num_enbs)],
        "site_id":   [f"SITE_{i:05d}" for i in range(1, num_enbs + 1)],
    })

    dim_cell = pl.DataFrame({
        "cell_id":     list(range(1, num_cells + 1)),
        "cell_name":   [f"cell_{i:05d}" for i in range(1, num_cells + 1)],
        "enb_id":      [((i - 1) % num_enbs) + 1 for i in range(1, num_cells + 1)],
        "sector":      [((i - 1) % 3) + 1 for i in range(1, num_cells + 1)],
        "earfcn":      [rng.choice([1800, 2600, 3500, 6300]) for _ in range(num_cells)],
        "archetype":   archetype_names,
        "latitude":    [round(51.5 + rng.uniform(-0.5, 0.5), 6) for _ in range(num_cells)],
        "longitude":   [round(-0.1 + rng.uniform(-0.5, 0.5), 6) for _ in range(num_cells)],
        "azimuth_deg": [rng.choice([0.0, 120.0, 240.0]) for _ in range(num_cells)],
        "created_at":  [now] * num_cells,
    })
    return dim_enb, dim_cell


# --- PM generation ---------------------------------------------------------

def _generate_pm_measurements(
    *,
    dim_cell: pl.DataFrame,
    start: datetime,
    num_days: int,
    rng: np.random.Generator,
) -> pl.DataFrame:
    """Generate baseline hourly counters for all cells."""
    hours = num_days * 24
    timestamps = hourly_range(start, hours)

    rows_out: list[dict] = []
    cell_rows = dim_cell.to_dicts()

    for cell in cell_rows:
        archetype: Archetype = ARCHETYPES[cell["archetype"]]  # type: ignore[index]
        for h_idx, ts in enumerate(timestamps):
            traffic_multiplier = (
                diurnal_factor(ts.hour, archetype.diurnal_amplitude)
                * weekly_factor(ts.weekday(), archetype.weekly_amplitude)
            )

            # Attempts scale with traffic
            rrc_att = int(archetype.peak_users * 3.0 * traffic_multiplier
                          * rng.normal(1.0, archetype.noise_stddev))
            rrc_att = max(0, rrc_att)

            # Successes: attempts × baseline success rate
            rrc_success_rate = archetype.base_accessibility_pct / 100.0
            rrc_succ = int(rrc_att * rrc_success_rate
                           * rng.normal(1.0, archetype.noise_stddev / 4))
            rrc_succ = min(rrc_succ, rrc_att)

            # E-RAB attempts roughly track RRC (each RRC → ~1.05 E-RABs)
            erab_att_init = int(rrc_att * 1.05
                                * rng.normal(1.0, archetype.noise_stddev / 4))
            erab_succ_init = int(erab_att_init * rrc_success_rate
                                 * rng.normal(1.0, archetype.noise_stddev / 4))
            erab_succ_init = min(erab_succ_init, erab_att_init)
            erab_att_added = int(erab_att_init * 0.3)
            erab_succ_added = int(erab_att_added * rrc_success_rate)
            erab_succ_added = min(erab_succ_added, erab_att_added)

            # E-RAB releases: total ≈ number of successful establishments
            erab_total_rel = max(1, erab_succ_init + erab_succ_added)
            erab_drop = archetype.base_drop_rate_pct / 100.0
            erab_rel_abnormal = int(erab_total_rel * erab_drop
                                    * rng.normal(1.0, archetype.noise_stddev))
            erab_rel_abnormal = max(0, erab_rel_abnormal)
            erab_rel_normal = erab_total_rel - erab_rel_abnormal

            # Handovers scale with traffic × mobility factor
            ho_att = int(rrc_att * 0.6 * traffic_multiplier)
            ho_succ_rate = archetype.base_ho_sr_pct / 100.0
            ho_succ = int(ho_att * ho_succ_rate)

            # Throughput: kbits per second summed over the hour
            pdcp_vol = (archetype.base_dl_throughput_kbps
                        * archetype.peak_users * 3600 * traffic_multiplier
                        * rng.normal(1.0, archetype.noise_stddev))
            ue_thp_time = int(archetype.peak_users * 3600 * traffic_multiplier * 0.4)

            # Availability: usually 3600 seconds; rare planned windows
            cell_downtime_auto = 0
            cell_downtime_man = 0

            for counter_name, value in [
                ("RRC_CONN_SETUP_ATT",     rrc_att),
                ("RRC_CONN_SETUP_SUCC",    rrc_succ),
                ("ERAB_ESTAB_ATT_INIT",    erab_att_init),
                ("ERAB_ESTAB_SUCC_INIT",   erab_succ_init),
                ("ERAB_ESTAB_ATT_ADDED",   erab_att_added),
                ("ERAB_ESTAB_SUCC_ADDED",  erab_succ_added),
                ("ERAB_REL_NORMAL_ENB",    erab_rel_normal),
                ("ERAB_REL_ABNORMAL_ENB",  erab_rel_abnormal),
                ("HO_EXEC_ATT_INTRA_LTE",  ho_att),
                ("HO_EXEC_SUCC_INTRA_LTE", ho_succ),
                ("PDCP_VOL_DL_DRB",        pdcp_vol),
                ("UE_THP_TIME_DL",         ue_thp_time),
                ("CELL_DOWNTIME_AUTO",     cell_downtime_auto),
                ("CELL_DOWNTIME_MAN",      cell_downtime_man),
            ]:
                rows_out.append({
                    "ts": ts,
                    "enb_id": cell["enb_id"],
                    "cell_id": cell["cell_id"],
                    "counter_id": COUNTERS[counter_name],
                    "value": float(value),
                    "gran_period_seconds": 3600,
                })

    return pl.DataFrame(rows_out)


# --- Anomaly overlay -------------------------------------------------------

# Maps KPI names to the counters that must move to make the KPI move.
KPI_TO_COUNTERS: dict[str, list[tuple[str, float]]] = {
    "rrc_conn_setup_sr":    [("RRC_CONN_SETUP_SUCC", -1.0)],
    "erab_setup_sr":        [("ERAB_ESTAB_SUCC_INIT", -1.0)],
    "erab_drop_rate":       [("ERAB_REL_ABNORMAL_ENB", +1.0),
                             ("ERAB_REL_NORMAL_ENB",   -0.5)],
    "intra_lte_ho_sr":      [("HO_EXEC_SUCC_INTRA_LTE", -1.0)],
    "dl_user_throughput":   [("PDCP_VOL_DL_DRB", -1.0)],
}


def _apply_anomalies(pm: pl.DataFrame, plan: AnomalyPlan) -> pl.DataFrame:
    """Apply each planned anomaly to the matching cell-hours."""
    if len(plan) == 0:
        return pm

    for anomaly in plan.anomalies:
        counter_moves = KPI_TO_COUNTERS.get(anomaly.kpi_affected, [])
        for counter_name, direction in counter_moves:
            counter_id = COUNTERS[counter_name]
            # `direction` = -1.0 means multiply by (1 - magnitude);
            #              +1.0 means multiply by (1 + magnitude × 5) (drops
            #              blow up abnormal releases sharply).
            if direction < 0:
                factor = 1.0 - anomaly.magnitude
            else:
                factor = 1.0 + anomaly.magnitude * 5

            mask = (
                (pl.col("cell_id") == anomaly.cell_id)
                & (pl.col("counter_id") == counter_id)
                & (pl.col("ts") >= anomaly.ts_start)
                & (pl.col("ts") < anomaly.ts_end)
            )
            pm = pm.with_columns(
                pl.when(mask)
                .then(pl.col("value") * factor)
                .otherwise(pl.col("value"))
                .alias("value")
            )

    return pm


# --- FM and CM -------------------------------------------------------------

def _generate_fm_alarms(
    dim_cell: pl.DataFrame,
    plan: AnomalyPlan,
    start: datetime,
    num_days: int,
    rng: random.Random,
) -> pl.DataFrame:
    """Generate FM alarms — some correlated with anomalies, some background."""
    rows: list[dict] = []
    uid = 1
    cell_lookup = {c["cell_id"]: c for c in dim_cell.to_dicts()}

    # Correlated alarms: emit an appropriate alarm just before each anomaly
    for a in plan.anomalies:
        if a.pattern_type in {"sudden_drop", "correlated_outage"}:
            enb_id = cell_lookup[a.cell_id]["enb_id"]
            alarm_type = _alarm_for_kpi(a.kpi_affected)
            rows.append({
                "alarm_uid": uid,
                "raised_at": a.ts_start - timedelta(minutes=rng.randint(2, 12)),
                "cleared_at": a.ts_end + timedelta(minutes=rng.randint(0, 20)),
                "enb_id": enb_id,
                "cell_id": a.cell_id,
                "alarm_type": alarm_type,
                "severity": rng.choice(["major", "critical"]),
                "source_system": "synth",
                "details": None,
            })
            uid += 1

    # Background noise: ~1 minor alarm per cell per week
    n_background = int(len(dim_cell) * num_days / 7)
    for _ in range(n_background):
        cell = rng.choice(list(cell_lookup.values()))
        raised = start + timedelta(
            days=rng.randint(0, num_days - 1),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        rows.append({
            "alarm_uid": uid,
            "raised_at": raised,
            "cleared_at": raised + timedelta(minutes=rng.randint(5, 120)),
            "enb_id": cell["enb_id"],
            "cell_id": cell["cell_id"],
            "alarm_type": rng.choice(["TEMPERATURE_HIGH", "VSWR_MINOR", "LICENSE_WARNING"]),
            "severity": rng.choice(["minor", "warning"]),
            "source_system": "synth",
            "details": None,
        })
        uid += 1

    return pl.DataFrame(rows)


def _alarm_for_kpi(kpi: str) -> str:
    return {
        "rrc_conn_setup_sr":   "S1_LINK_DOWN",
        "erab_setup_sr":       "S1_TRANSPORT_FAILURE",
        "erab_drop_rate":      "BOARD_FAULT",
        "intra_lte_ho_sr":     "X2_NEIGHBOUR_TIMEOUT",
        "dl_user_throughput":  "RRU_TEMPERATURE_HIGH",
    }.get(kpi, "GENERIC_FAULT")


def _generate_cm_changes(
    dim_cell: pl.DataFrame,
    start: datetime,
    num_days: int,
    rng: random.Random,
) -> pl.DataFrame:
    """Sparse configuration changes — ~1 change per 10 cells per week."""
    rows: list[dict] = []
    uid = 1
    n = max(1, len(dim_cell) * num_days // 70)
    cells = dim_cell.to_dicts()
    for _ in range(n):
        cell = rng.choice(cells)
        changed_at = start + timedelta(
            days=rng.randint(0, num_days - 1),
            hours=rng.randint(6, 20),
        )
        param = rng.choice(["cellIndividualOffset", "qOffsetCell", "tac", "pMax"])
        rows.append({
            "change_uid": uid,
            "cell_id": cell["cell_id"],
            "parameter": param,
            "old_value": str(rng.randint(-10, 0)),
            "new_value": str(rng.randint(-10, 10)),
            "changed_at": changed_at,
            "changed_by": rng.choice(["planning_tool", "manual_op", "sonauto"]),
        })
        uid += 1
    return pl.DataFrame(rows)


# --- Load orchestration ----------------------------------------------------

def generate_and_load(
    *,
    num_cells: int | None = None,
    num_days: int | None = None,
    seed: int | None = None,
) -> None:
    """Generate synthetic data and bulk-load it into Postgres."""
    from telcoscope.synth.loader import bulk_load

    data = generate(
        num_cells=num_cells or settings.synth_num_cells,
        num_days=num_days or settings.synth_days,
        seed=seed if seed is not None else settings.synth_seed,
    )
    bulk_load(data)
    logger.success("Synthetic data generation and load complete.")


if __name__ == "__main__":
    generate_and_load()