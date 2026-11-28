"""Unit tests for the RCA engine.

These exercise ``evaluate_incident`` with a monkey-patched
``resolve`` so the engine logic (AND semantics, weakest-link
confidence, ranking, top-N) is tested without a live database. A
single DB-driven smoke test at the end proves the real engine flow
runs against the seeded data when ``analytics.incidents`` has rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from telcoscope.config import settings
from telcoscope.rca.engine import (
    DEFAULT_RULES_PATH,
    Hypothesis,
    evaluate_incident,
    load_rules,
)
from telcoscope.rca.schema import AlarmTrigger, Rule, RuleLibrary
from telcoscope.rca.triggers.base import MatchResult

# ---------------------------------------------------------------------
# Rule-loading tests
# ---------------------------------------------------------------------


def test_load_rules_default_path_returns_five_rules():
    """The shipped rules.yaml loads cleanly and contains all 5 rules."""
    library = load_rules()
    assert isinstance(library, RuleLibrary)
    assert len(library.rules) == 5
    ids = [r.id for r in library.rules]
    assert ids == ["rca_001", "rca_002", "rca_003", "rca_004", "rca_005"]


def test_load_rules_default_path_exists():
    """Sanity: the default path is where we think it is."""
    assert DEFAULT_RULES_PATH.name == "rules.yaml"
    assert DEFAULT_RULES_PATH.is_file()


# ---------------------------------------------------------------------
# Helpers for the mocked-resolver tests
# ---------------------------------------------------------------------


def _make_rule(
    rule_id: str = "test_rule",
    confidence: float = 1.0,
    num_triggers: int = 1,
) -> Rule:
    """Build a Rule with ``num_triggers`` AlarmTrigger instances."""
    return Rule(
        id=rule_id,
        name=f"Test rule {rule_id}",
        kpis_affected=["rrc_conn_setup_sr"],
        triggers=[
            AlarmTrigger(
                alarm_pattern="TEST.*",
                within_minutes=15,
                severity_min="minor",
                scope="same_cell",
            )
            for _ in range(num_triggers)
        ],
        likely_cause="Synthetic test rule",
        confidence=confidence,
        suggested_actions=["Do a test thing"],
        evidence_template=None,
    )


INCIDENT: dict[str, Any] = {
    "incident_id": "11111111-1111-1111-1111-111111111111",
    "cell_id": 42,
    "ts_start": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    "ts_end": datetime(2026, 11, 1, 10, 30, tzinfo=UTC),
}


# ---------------------------------------------------------------------
# AND-semantics + ranking + top-N
# ---------------------------------------------------------------------


def test_no_rules_returns_empty_list():
    """An empty library yields no hypotheses."""
    result = evaluate_incident(INCIDENT, RuleLibrary(rules=[]), conn=None)  # type: ignore[arg-type]
    assert result == []


def test_single_rule_all_triggers_match(monkeypatch):
    """A rule with one matching trigger returns one hypothesis."""
    rule = _make_rule(rule_id="r1", confidence=0.8, num_triggers=1)

    monkeypatch.setattr(
        "telcoscope.rca.engine.resolve",
        lambda incident, trigger, conn: MatchResult(
            evidence={"alarm_uid": 1},
            strength=1.0,
        ),
    )

    result = evaluate_incident(INCIDENT, [rule], conn=None)  # type: ignore[arg-type]
    assert len(result) == 1
    h = result[0]
    assert isinstance(h, Hypothesis)
    assert h.rule_id == "r1"
    assert h.confidence == 0.8  # 0.8 * min(1.0) = 0.8
    assert h.evidence["rule_snapshot"]["name"] == "Test rule r1"
    assert h.evidence["triggers"][0]["type"] == "concurrent_fm_alarm"
    assert h.evidence["triggers"][0]["alarm_uid"] == 1


def test_any_trigger_none_skips_rule(monkeypatch):
    """AND semantics: one None return means the rule does not fire."""
    rule = _make_rule(rule_id="r_and", confidence=0.9, num_triggers=2)

    # First trigger matches, second returns None.
    call_count = {"n": 0}

    def mock_resolve(incident, trigger, conn):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MatchResult(evidence={"alarm_uid": 1}, strength=1.0)
        return None

    monkeypatch.setattr("telcoscope.rca.engine.resolve", mock_resolve)

    result = evaluate_incident(INCIDENT, [rule], conn=None)  # type: ignore[arg-type]
    assert result == []


def test_min_strength_caps_confidence(monkeypatch):
    """Final confidence = rule.confidence × min(trigger strengths)."""
    rule = _make_rule(rule_id="r_min", confidence=1.0, num_triggers=3)

    strengths = iter([0.9, 0.3, 0.7])

    def mock_resolve(incident, trigger, conn):
        return MatchResult(evidence={}, strength=next(strengths))

    monkeypatch.setattr("telcoscope.rca.engine.resolve", mock_resolve)

    result = evaluate_incident(INCIDENT, [rule], conn=None)  # type: ignore[arg-type]
    assert len(result) == 1
    # weakest trigger (0.3) sets the cap: 1.0 × 0.3 = 0.3
    assert result[0].confidence == 0.3


def test_hypotheses_sorted_by_confidence_desc(monkeypatch):
    """Output is sorted most-confident first."""
    rules = [
        _make_rule(rule_id="low", confidence=0.3),
        _make_rule(rule_id="high", confidence=0.9),
        _make_rule(rule_id="mid", confidence=0.6),
    ]

    monkeypatch.setattr(
        "telcoscope.rca.engine.resolve",
        lambda incident, trigger, conn: MatchResult(evidence={}, strength=1.0),
    )

    result = evaluate_incident(INCIDENT, rules, conn=None)  # type: ignore[arg-type]
    assert [h.rule_id for h in result] == ["high", "mid", "low"]
    assert [h.confidence for h in result] == [0.9, 0.6, 0.3]


def test_top_n_truncates(monkeypatch):
    """Only the top N hypotheses are returned."""
    rules = [_make_rule(rule_id=f"r{i}", confidence=0.1 * (i + 1)) for i in range(10)]

    monkeypatch.setattr(
        "telcoscope.rca.engine.resolve",
        lambda incident, trigger, conn: MatchResult(evidence={}, strength=1.0),
    )

    result = evaluate_incident(INCIDENT, rules, conn=None, top_n=3)  # type: ignore[arg-type]
    assert len(result) == 3
    assert [h.rule_id for h in result] == ["r9", "r8", "r7"]


def test_rule_snapshot_captures_human_readable_fields(monkeypatch):
    """Evidence captures rule.name / likely_cause / suggested_actions."""
    rule = _make_rule(rule_id="r_snap", confidence=0.5)

    monkeypatch.setattr(
        "telcoscope.rca.engine.resolve",
        lambda incident, trigger, conn: MatchResult(evidence={"alarm_uid": 99}, strength=1.0),
    )

    [h] = evaluate_incident(INCIDENT, [rule], conn=None)  # type: ignore[arg-type]
    snap = h.evidence["rule_snapshot"]
    assert snap["name"] == "Test rule r_snap"
    assert snap["likely_cause"] == "Synthetic test rule"
    assert snap["suggested_actions"] == ["Do a test thing"]
    assert snap["evidence_template"] is None


# ---------------------------------------------------------------------
# DB-driven smoke test — runs only when analytics.incidents has rows
# ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def conn():
    dsn = settings.postgres_url.replace("+psycopg", "")
    with psycopg.connect(dsn) as c:
        yield c


@pytest.fixture(scope="module")
def sample_incident(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT incident_id, cell_id, ts_start, ts_end
            FROM analytics.incidents
            ORDER BY ts_start DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("No incidents in analytics.incidents — run `make incidents` first.")
    incident_id, cell_id, ts_start, ts_end = row
    return {
        "incident_id": str(incident_id),
        "cell_id": cell_id,
        "ts_start": ts_start,
        "ts_end": ts_end,
    }


def test_evaluate_incident_against_real_db(conn, sample_incident):
    """End-to-end smoke: load real rules, evaluate real incident, no crash."""
    library = load_rules()
    result = evaluate_incident(sample_incident, library, conn)
    assert isinstance(result, list)
    # Zero hypotheses is a valid result (no rules fired). All we check
    # is that each entry is well-formed if any came back.
    for h in result:
        assert isinstance(h, Hypothesis)
        assert 0.0 <= h.confidence <= 1.0
        assert "rule_snapshot" in h.evidence
        assert "triggers" in h.evidence
