"""RCA engine — rules-first, per-incident, ranked hypothesis retriever.

Loads the rule library from YAML (pydantic-validated), evaluates every
rule against one incident, and returns the top-N hypotheses ordered by
confidence. See DEC-006 for the architecture and semantics.

The engine is intentionally single-incident: iteration over incidents
and persistence of hypotheses live in ``incidents.rca_run`` /
``rca.persistence`` so this module stays a pure retriever.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from psycopg import Connection

from telcoscope.rca.schema import Rule, RuleLibrary
from telcoscope.rca.triggers import resolve

DEFAULT_RULES_PATH = Path(__file__).parent / "rules.yaml"
DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class Hypothesis:
    """A single ranked RCA hypothesis for an incident.

    Attributes:
        rule_id: The rule's ``id`` from ``rules.yaml``. Stored as the
            FK-like column ``analytics.rca_hypotheses.rule_id``.
        confidence: Final confidence in [0, 1], computed as
            ``rule.confidence * min(trigger strengths)``. Stored in
            ``analytics.rca_hypotheses.confidence``.
        evidence: JSONB payload for
            ``analytics.rca_hypotheses.evidence``. Contains two keys:

            - ``rule_snapshot``: the rule's human-readable fields at
              generation time (``name``, ``likely_cause``,
              ``suggested_actions``, ``evidence_template``). Captured
              so a stored hypothesis stays interpretable after the
              rule library changes.
            - ``triggers``: a list of per-trigger evidence dicts, each
              tagged with its ``type``, in the order they appear on
              the rule.
    """

    rule_id: str
    confidence: float
    evidence: dict[str, Any]


def load_rules(path: Path | str = DEFAULT_RULES_PATH) -> RuleLibrary:
    """Load and validate the RCA rule library from YAML.

    Reads ``path``, runs ``yaml.safe_load`` on the contents, and
    passes the result through ``RuleLibrary.model_validate`` so any
    malformed rule is rejected at startup rather than silently at
    evaluation time.
    """
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    library = RuleLibrary.model_validate(data)
    logger.info("Loaded {} RCA rules from {}", len(library.rules), path)
    return library


def evaluate_incident(
    incident: dict[str, Any],
    rules: RuleLibrary | list[Rule],
    conn: Connection,
    *,
    top_n: int = DEFAULT_TOP_N,
) -> list[Hypothesis]:
    """Evaluate every rule against one incident, return top-N hypotheses.

    A rule fires only when ALL its triggers resolve to a
    ``MatchResult`` (AND semantics — matches the rules.yaml header
    comment). The hypothesis confidence is
    ``rule.confidence * min(trigger strengths)`` — the weakest-link
    rule caps the final confidence, which is easier to reason about
    than a mean or product aggregation.

    Hypotheses are sorted by confidence descending; input rule order
    breaks ties. The result is sliced to ``top_n`` entries.
    """
    rule_list = rules.rules if isinstance(rules, RuleLibrary) else rules
    hypotheses: list[Hypothesis] = []

    for rule in rule_list:
        matches = [resolve(incident, trigger, conn) for trigger in rule.triggers]
        if any(m is None for m in matches):
            # AND semantics: one None means the rule does not fire.
            continue

        strengths = [m.strength for m in matches]  # type: ignore[union-attr]
        min_strength = min(strengths)
        confidence = round(rule.confidence * min_strength, 4)

        evidence: dict[str, Any] = {
            "rule_snapshot": {
                "name": rule.name,
                "likely_cause": rule.likely_cause,
                "suggested_actions": list(rule.suggested_actions),
                "evidence_template": rule.evidence_template,
            },
            "triggers": [
                {"type": trigger.type, **m.evidence}  # type: ignore[union-attr]
                for trigger, m in zip(rule.triggers, matches, strict=True)
            ],
        }

        hypotheses.append(
            Hypothesis(
                rule_id=rule.id,
                confidence=confidence,
                evidence=evidence,
            )
        )

    # Stable sort by confidence desc; rule-library order breaks ties.
    hypotheses.sort(key=lambda h: -h.confidence)
    return hypotheses[:top_n]
