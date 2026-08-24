"""LLM-driven incident narrator.

Generates human-readable incident summaries by passing the structured incident
record (anomaly + ranked RCA hypotheses + supporting evidence) to a Claude
model via the Anthropic API.

Has two modes, configured via ``settings.narrator_mode``:

- ``mock``: returns a deterministic, template-based summary. Used in CI and
  when no API key is configured.
- ``live``: calls the Anthropic API. Requires ``settings.anthropic_api_key``.

The mock mode is the default — the live mode is opt-in to avoid surprising
the user with API charges.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from telcoscope.config import settings


SYSTEM_PROMPT = """\
You are a mobile network operations analyst writing an incident summary for an \
on-call engineer. The engineer is technically literate, knows LTE / 3GPP \
terminology, and will read your summary on a phone at 3 a.m.

Your output must be:
- One paragraph, plain prose, 80–120 words.
- Lead with what happened, then where, then likely cause, then suggested action.
- No bullets, no headers, no greetings, no "I" or "we".
- Cite specific evidence (alarm types, parameter changes, neighbour cells) \
when present.
- If confidence in the root cause is low, say so explicitly.
"""


def narrate(incident: dict[str, Any]) -> str:
    """Produce a human-readable incident narrative.

    Parameters
    ----------
    incident:
        Structured incident record. Expected keys: ``anomaly``, ``hypotheses``,
        ``alarms``, ``cm_changes``, ``neighbour_anomalies``, ``cell_context``.

    Returns
    -------
    A short paragraph describing the incident for an on-call engineer.
    """
    if settings.narrator_mode == "mock" or not settings.anthropic_api_key:
        return _mock_narrate(incident)
    return _live_narrate(incident)


def _mock_narrate(incident: dict[str, Any]) -> str:
    """Deterministic, template-based narrative for CI / offline use."""
    anomaly = incident.get("anomaly", {})
    kpi = anomaly.get("kpi_name", "an unspecified KPI")
    cell = anomaly.get("cell_id", "?")
    severity = anomaly.get("severity", "unknown")
    value = anomaly.get("kpi_value", "?")
    baseline = anomaly.get("baseline", "?")

    hypotheses = incident.get("hypotheses", [])
    top_cause = hypotheses[0]["likely_cause"] if hypotheses else "no clear cause identified"
    top_confidence = (
        hypotheses[0].get("confidence", 0.0) if hypotheses else 0.0
    )

    return (
        f"[MOCK] {severity.title()} {kpi} degradation detected on cell {cell} "
        f"(observed {value}, baseline {baseline}). Most likely cause: "
        f"{top_cause} (confidence {top_confidence:.0%}). Review recent alarms "
        f"and configuration changes on the affected element."
    )


def _live_narrate(incident: dict[str, Any]) -> str:
    """Live call to the Anthropic API."""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed; falling back to mock")
        return _mock_narrate(incident)

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_content = _format_incident_for_prompt(incident)

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Extract text from the first content block.
    parts = [b.text for b in message.content if b.type == "text"]
    return "".join(parts).strip()


def _format_incident_for_prompt(incident: dict[str, Any]) -> str:
    """Render an incident dict into a human-readable prompt block."""
    import json
    return (
        "Incident details (JSON):\n\n"
        f"{json.dumps(incident, indent=2, default=str)}\n\n"
        "Write the incident summary."
    )
