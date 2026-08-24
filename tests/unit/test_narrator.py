"""Tests for the LLM incident narrator (mock mode only)."""
from __future__ import annotations

from telcoscope.narrate.llm import narrate


def test_narrator_returns_string(sample_incident: dict) -> None:
    """Mock narrator returns a non-empty string."""
    out = narrate(sample_incident)
    assert isinstance(out, str)
    assert len(out) > 10


def test_narrator_includes_kpi_name(sample_incident: dict) -> None:
    """Mock narrative mentions the affected KPI."""
    out = narrate(sample_incident)
    assert "rrc_conn_setup_sr" in out


def test_narrator_handles_empty_hypotheses(sample_incident: dict) -> None:
    """Narrator does not crash when no RCA hypotheses are present."""
    sample_incident["hypotheses"] = []
    out = narrate(sample_incident)
    assert isinstance(out, str)
    assert len(out) > 10
