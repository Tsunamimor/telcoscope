"""Pydantic models for the RCA rule library.

Used by ``rca.engine`` to validate ``rules.yaml`` at load time, ensuring rule
authors can't accidentally introduce malformed rules into production.

The trigger union is **discriminated** on the ``type`` field — every trigger
entry in the YAML must declare its ``type`` (one of ``concurrent_fm_alarm``,
``recent_cm_change``, ``neighbour_cell_anomaly``, ``kpi_pattern``). This makes
pydantic parse each trigger directly to the correct subclass rather than
guess, so typos surface as clear "unknown discriminator value" errors
instead of validation failures scattered across every subclass.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Severity = Literal["warning", "minor", "major", "critical"]
Scope = Literal["same_cell", "same_enb", "same_region"]
KpiDirection = Literal["drop", "spike"]


class AlarmTrigger(BaseModel):
    """Trigger that fires on a concurrent FM alarm matching a pattern."""

    type: Literal["concurrent_fm_alarm"] = "concurrent_fm_alarm"
    alarm_pattern: str
    within_minutes: int = Field(gt=0, le=24 * 60)
    severity_min: Severity = "minor"
    scope: Scope = "same_cell"


class CmChangeTrigger(BaseModel):
    """Trigger that fires on a recent CM change."""

    type: Literal["recent_cm_change"] = "recent_cm_change"
    cm_change_within_minutes: int = Field(gt=0, le=24 * 60)
    parameter: str | None = None
    scope: Scope = "same_cell"


class NeighbourAnomalyTrigger(BaseModel):
    """Trigger that fires on N or more anomalies on neighbour cells."""

    type: Literal["neighbour_cell_anomaly"] = "neighbour_cell_anomaly"
    neighbour_anomalies_min: int = Field(ge=1)
    within_minutes: int = Field(gt=0, le=24 * 60)
    scope: Scope = "same_enb"


class KpiPatternTrigger(BaseModel):
    """Trigger that fires on a specific KPI drop/spike at incident start.

    Matches when the named KPI shows a drop (or spike) of at least
    ``magnitude_pct`` versus the pre-incident baseline at the incident's
    ``ts_start`` on the same cell. Useful for rules that key off a signature
    pattern rather than a correlated event (e.g. "sudden 50% RRC drop with
    no alarm = PRB congestion").
    """

    type: Literal["kpi_pattern"] = "kpi_pattern"
    kpi: str
    direction: KpiDirection
    magnitude_pct: float = Field(gt=0.0, le=100.0)
    scope: Scope = "same_cell"


Trigger = Annotated[
    AlarmTrigger | CmChangeTrigger | NeighbourAnomalyTrigger | KpiPatternTrigger,
    Field(discriminator="type"),
]


class Rule(BaseModel):
    """A single RCA rule.

    The ``confidence`` field is the rule's **base confidence** — the value
    stored into ``analytics.rca_hypotheses.confidence`` after the engine
    multiplies it by the per-match ``match_strength`` from the triggers that
    fired. See DEC-006 §3 for the full semantics.
    """

    id: str
    name: str
    kpis_affected: list[str]
    triggers: list[Trigger]
    likely_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_actions: list[str]
    evidence_template: str | None = None


class RuleLibrary(BaseModel):
    """Top-level container loaded from ``rules.yaml``."""

    rules: list[Rule]
