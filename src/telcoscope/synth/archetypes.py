"""Cell archetypes for the synthetic data generator.

Defines representative profiles for different deployment scenarios. Each
archetype establishes baseline behaviour (peak traffic, diurnal shape, noise
floor) so that anomaly detection can be evaluated against realistic-looking
seasonality rather than uniform noise.

These archetypes are intentionally stylised — they capture the *shape* of
real-world deployment patterns without claiming to match any particular
operator's data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ArchetypeName = Literal["urban_dense", "urban", "suburban", "rural"]


@dataclass(frozen=True)
class Archetype:
    """A cell deployment archetype.

    Attributes
    ----------
    name:
        Identifier used in `dim_cell.archetype`.
    peak_users:
        Approximate peak concurrent users in busy hour.
    diurnal_amplitude:
        Fraction by which traffic varies around the mean over 24h (0.0–1.0).
    weekly_amplitude:
        Fraction by which weekend traffic differs from weekday (e.g. 0.3 = 30%
        lower at weekends for typical business-district urban).
    base_accessibility_pct:
        Baseline RRC connection setup success rate (%). Will be perturbed.
    base_drop_rate_pct:
        Baseline E-RAB drop rate (%).
    base_ho_sr_pct:
        Baseline intra-LTE handover success rate (%).
    base_dl_throughput_kbps:
        Baseline per-user DL throughput at typical load (kbps).
    noise_stddev:
        Standard deviation of multiplicative noise applied to counter values.
    """

    name: ArchetypeName
    peak_users: int
    diurnal_amplitude: float
    weekly_amplitude: float
    base_accessibility_pct: float
    base_drop_rate_pct: float
    base_ho_sr_pct: float
    base_dl_throughput_kbps: float
    noise_stddev: float


ARCHETYPES: dict[ArchetypeName, Archetype] = {
    "urban_dense": Archetype(
        name="urban_dense",
        peak_users=400,
        diurnal_amplitude=0.65,
        weekly_amplitude=0.25,
        base_accessibility_pct=99.4,
        base_drop_rate_pct=0.35,
        base_ho_sr_pct=98.7,
        base_dl_throughput_kbps=12_000,
        noise_stddev=0.04,
    ),
    "urban": Archetype(
        name="urban",
        peak_users=220,
        diurnal_amplitude=0.55,
        weekly_amplitude=0.20,
        base_accessibility_pct=99.5,
        base_drop_rate_pct=0.30,
        base_ho_sr_pct=98.9,
        base_dl_throughput_kbps=18_000,
        noise_stddev=0.03,
    ),
    "suburban": Archetype(
        name="suburban",
        peak_users=120,
        diurnal_amplitude=0.45,
        weekly_amplitude=0.10,
        base_accessibility_pct=99.7,
        base_drop_rate_pct=0.22,
        base_ho_sr_pct=99.2,
        base_dl_throughput_kbps=22_000,
        noise_stddev=0.03,
    ),
    "rural": Archetype(
        name="rural",
        peak_users=40,
        diurnal_amplitude=0.35,
        weekly_amplitude=-0.05,  # weekend traffic slightly HIGHER (leisure)
        base_accessibility_pct=99.8,
        base_drop_rate_pct=0.18,
        base_ho_sr_pct=99.4,
        base_dl_throughput_kbps=28_000,
        noise_stddev=0.025,
    ),
}


def archetype_distribution() -> dict[ArchetypeName, float]:
    """Default mix of archetypes across the synthetic cell population.

    Roughly reflective of a Tier 1 European operator's network composition,
    skewed slightly toward urban for analytical interest.
    """
    return {
        "urban_dense": 0.15,
        "urban": 0.35,
        "suburban": 0.30,
        "rural": 0.20,
    }
