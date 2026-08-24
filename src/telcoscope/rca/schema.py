"""Pydantic models for the RCA rule library.

Used by ``rca.engine`` to validate ``rules.yaml`` at load time, ensuring rule
authors can't accidentally introduce malformed rules into production.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["warning", "minor", "major", "critical"]
Scope = Literal["same_cell", "same_enb", "same_region"]


class AlarmTrigger(BaseModel):
    """Trigger that fires on a concurrent FM alarm matching a pattern."""

    alarm_pattern: str
    within_minutes: int = Field(gt=0, le=24 * 60)
    severity_min: Severity = "minor"
    scope: Scope = "same_cell"


class CmChangeTrigger(BaseModel):
    """Trigger that fires on a recent CM change."""

    cm_change_within_minutes: int = Field(gt=0, le=24 * 60)
    parameter: str | None = None
    scope: Scope = "same_cell"


class NeighbourAnomalyTrigger(BaseModel):
    """Trigger that fires on N or more anomalies on neighbour cells."""

    neighbour_anomalies_min: int = Field(ge=1)
    within_minutes: int = Field(gt=0, le=24 * 60)
    scope: Scope = "same_enb"


Trigger = AlarmTrigger | CmChangeTrigger | NeighbourAnomalyTrigger


class Rule(BaseModel):
    """A single RCA rule."""

    id: str
    name: str
    kpis_affected: list[str]
    triggers: list[Trigger]
    likely_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_actions: list[str]


class RuleLibrary(BaseModel):
    """Top-level container loaded from ``rules.yaml``."""

    rules: list[Rule]
