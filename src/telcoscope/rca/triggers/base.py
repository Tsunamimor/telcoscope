"""Shared types for RCA trigger resolvers.

A resolver takes an incident row and a pydantic trigger config, queries
the right source table for evidence of the trigger's condition, and
returns either None (no match) or a MatchResult with evidence (dict,
serialised to JSONB in analytics.rca_hypotheses) and strength (float
in [0, 1], multiplied by the rule's base confidence to produce the
final hypothesis confidence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MatchResult:
    """Resolver output on a successful match.

    Attributes:
        evidence: Structured facts describing the match. Serialised to
            JSONB in ``analytics.rca_hypotheses.evidence``. Keys are
            resolver-specific but should be snake_case human-readable
            fact names.
        strength: Match quality in [0, 1]. See per-resolver docstrings
            for the exact semantics (temporal proximity, above-threshold
            boost, magnitude ratio, etc.). Multiplied by the rule's base
            confidence to produce the hypothesis confidence stored on
            ``analytics.rca_hypotheses``.
    """

    evidence: dict[str, Any]
    strength: float
