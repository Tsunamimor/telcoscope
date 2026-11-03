"""Smoke tests for RCA trigger resolvers.

These exercise each resolver's SQL against the live DB with a real
incident fetched from ``analytics.incidents``. They assert that the
query compiles and either returns ``None`` or a well-formed
``MatchResult`` with a strength in the documented range. They do not
assert specific match outcomes — rigorous unit tests driven by
controlled fixture data come in a later commit (see DEC-006 §6 step 7).

The suite is skipped if ``analytics.incidents`` is empty, so these
tests do not run until ``make incidents`` has been executed at least
once.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from telcoscope.config import settings
from telcoscope.rca.schema import (
    AlarmTrigger,
    CmChangeTrigger,
    KpiPatternTrigger,
    NeighbourAnomalyTrigger,
)
from telcoscope.rca.triggers import MatchResult, resolve
from telcoscope.rca.triggers.kpi_pattern import resolve_kpi_pattern


@pytest.fixture(scope="module")
def conn():
    """Open one psycopg connection reused across the module."""
    dsn = settings.postgres_url.replace("+psycopg", "")
    with psycopg.connect(dsn) as c:
        yield c


@pytest.fixture(scope="module")
def sample_incident(conn):
    """Fetch the most recent incident, or skip the suite if none exist."""
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


def test_alarm_resolver_smoke(conn, sample_incident):
    """resolve_alarm returns None or a well-formed MatchResult."""
    trigger = AlarmTrigger(
        alarm_pattern="S1.*",
        within_minutes=15,
        severity_min="minor",
        scope="same_enb",
    )
    result = resolve(sample_incident, trigger, conn)
    assert result is None or isinstance(result, MatchResult)
    if result is not None:
        assert 0.0 <= result.strength <= 1.0
        assert "alarm_uid" in result.evidence
        assert "delta_minutes" in result.evidence


def test_cm_change_resolver_smoke(conn, sample_incident):
    """resolve_cm_change returns None or a well-formed MatchResult."""
    trigger = CmChangeTrigger(
        cm_change_within_minutes=60,
        scope="same_cell",
    )
    result = resolve(sample_incident, trigger, conn)
    assert result is None or isinstance(result, MatchResult)
    if result is not None:
        assert 0.0 <= result.strength <= 1.0
        assert "change_uid" in result.evidence
        assert "parameter" in result.evidence


def test_neighbour_resolver_smoke(conn, sample_incident):
    """resolve_neighbour returns None or a MatchResult with strength >= 0.5."""
    trigger = NeighbourAnomalyTrigger(
        neighbour_anomalies_min=3,
        within_minutes=15,
        scope="same_enb",
    )
    result = resolve(sample_incident, trigger, conn)
    assert result is None or isinstance(result, MatchResult)
    if result is not None:
        # Above-threshold strength floor is 0.5.
        assert 0.5 <= result.strength <= 1.0
        assert result.evidence["neighbour_cell_count"] >= 3


def test_kpi_pattern_resolver_smoke(conn, sample_incident):
    """resolve_kpi_pattern returns None or a well-formed MatchResult."""
    trigger = KpiPatternTrigger(
        kpi="rrc_conn_setup_sr",
        direction="drop",
        magnitude_pct=10.0,
        scope="same_cell",
    )
    result = resolve(sample_incident, trigger, conn)
    assert result is None or isinstance(result, MatchResult)
    if result is not None:
        assert 0.0 <= result.strength <= 1.0
        assert "pct_change" in result.evidence
        assert result.evidence["pct_change"] < 0  # direction="drop"


def test_kpi_pattern_rejects_unknown_kpi_name():
    """resolve_kpi_pattern guards against KPI names outside the allow-list.

    Pydantic lets any string into KpiPatternTrigger.kpi; the resolver
    enforces an allow-list before building SQL. This is the defence
    against injection via that field.
    """
    trigger = KpiPatternTrigger(
        kpi="not_a_real_kpi",
        direction="drop",
        magnitude_pct=10.0,
    )
    with pytest.raises(ValueError, match="Unknown KPI"):
        resolve_kpi_pattern(
            {"cell_id": 1, "ts_start": datetime(2026, 1, 1, tzinfo=UTC)},
            trigger,
            None,  # type: ignore[arg-type]
        )
