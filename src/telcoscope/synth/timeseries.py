"""Time-series helpers for the synthetic generator.

Encapsulates seasonality math and noise so `generator.py` stays readable.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np

# Peak-hour convention: 20:00 local (evening peak typical for consumer traffic).
_PEAK_HOUR = 20.0


def diurnal_factor(hour_of_day: int, amplitude: float) -> float:
    """Return a multiplier in [1 - amplitude, 1 + amplitude] for the given hour.

    Uses a cosine curve centred on `_PEAK_HOUR`.
    """
    phase = (hour_of_day - _PEAK_HOUR) / 24.0
    return 1.0 + amplitude * math.cos(2 * math.pi * phase)


def weekly_factor(day_of_week: int, weekly_amplitude: float) -> float:
    """Return a multiplier for a given weekday.

    Weekdays (Mon–Fri) sit at `1 + weekly_amplitude`, weekends at
    `1 - weekly_amplitude`. For archetypes where `weekly_amplitude` is
    negative (rural), the sense inverts naturally.
    """
    is_weekend = day_of_week >= 5  # Saturday=5, Sunday=6
    return 1.0 - weekly_amplitude if is_weekend else 1.0 + weekly_amplitude


def noise(rng: np.random.Generator, size: int, stddev: float) -> np.ndarray:
    """Return multiplicative noise centred on 1.0."""
    return np.clip(rng.normal(loc=1.0, scale=stddev, size=size), 0.0, None)


def hourly_range(start: datetime, hours: int) -> list[datetime]:
    """Return `hours` evenly spaced datetimes starting at `start`."""
    from datetime import timedelta
    return [start + timedelta(hours=h) for h in range(hours)]