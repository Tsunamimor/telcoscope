"""RCA trigger resolvers.

Dispatches a parsed Trigger (one of ``AlarmTrigger``,
``CmChangeTrigger``, ``NeighbourAnomalyTrigger``, ``KpiPatternTrigger``)
to the matching resolver, which queries the right source table and
returns a ``MatchResult`` if the trigger condition fires on the given
incident.

The dispatch uses ``type(trigger)`` rather than reflection on the
``type`` discriminator field so a new trigger type is wired in by
adding both the pydantic class *and* the resolver mapping entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from psycopg import Connection

from telcoscope.rca.schema import (
    AlarmTrigger,
    CmChangeTrigger,
    KpiPatternTrigger,
    NeighbourAnomalyTrigger,
    Trigger,
)
from telcoscope.rca.triggers.alarm import resolve_alarm
from telcoscope.rca.triggers.base import MatchResult
from telcoscope.rca.triggers.cm_change import resolve_cm_change
from telcoscope.rca.triggers.kpi_pattern import resolve_kpi_pattern
from telcoscope.rca.triggers.neighbour import resolve_neighbour

_Resolver = Callable[[dict[str, Any], Any, Connection], MatchResult | None]

_RESOLVERS: dict[type, _Resolver] = {
    AlarmTrigger: resolve_alarm,
    CmChangeTrigger: resolve_cm_change,
    NeighbourAnomalyTrigger: resolve_neighbour,
    KpiPatternTrigger: resolve_kpi_pattern,
}


def resolve(
    incident: dict[str, Any],
    trigger: Trigger,
    conn: Connection,
) -> MatchResult | None:
    """Dispatch a parsed trigger to its matching resolver function."""
    resolver = _RESOLVERS[type(trigger)]
    return resolver(incident, trigger, conn)


__all__ = [
    "MatchResult",
    "resolve",
    "resolve_alarm",
    "resolve_cm_change",
    "resolve_kpi_pattern",
    "resolve_neighbour",
]
