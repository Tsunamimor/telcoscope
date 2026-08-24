"""Shared pytest fixtures."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def sample_incident() -> dict:
    """A minimal incident record suitable for narrator tests."""
    return {
        "anomaly": {
            "kpi_name": "rrc_conn_setup_sr",
            "cell_id": 42,
            "severity": "major",
            "kpi_value": 87.3,
            "baseline": 99.4,
            "ts": datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc),
        },
        "hypotheses": [
            {
                "rule_id": "rca_001",
                "likely_cause": "S1 transport degradation between eNB and EPC",
                "confidence": 0.85,
                "evidence": ["S1_LINK_DOWN alarm on eNB 7"],
            }
        ],
        "alarms": [
            {"alarm_type": "S1_LINK_DOWN", "severity": "major", "raised_at": "..."}
        ],
        "cm_changes": [],
        "neighbour_anomalies": [],
        "cell_context": {"archetype": "urban", "enb_id": 7},
    }
