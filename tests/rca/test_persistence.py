"""Integration tests for RCA hypothesis persistence.

These write and read ``analytics.rca_hypotheses`` against the live DB
using a real ``incident_id`` picked from ``analytics.incidents``. The
``test_incident_id`` fixture deletes any hypothesis rows it produced
during teardown, so a failing test still leaves the DB in the state
it found.

Suite skips when ``analytics.incidents`` is empty — run
``make incidents`` first in that case.
"""

from __future__ import annotations

import psycopg
import pytest

from telcoscope.config import settings
from telcoscope.rca.engine import Hypothesis
from telcoscope.rca.persistence import persist_hypotheses


@pytest.fixture(scope="module")
def conn():
    dsn = settings.postgres_url.replace("+psycopg", "")
    with psycopg.connect(dsn) as c:
        yield c


@pytest.fixture
def test_incident_id(conn):
    """Pick a real incident_id, clean up rca_hypotheses for it on teardown."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT incident_id
            FROM analytics.incidents
            ORDER BY ts_start DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("No incidents in analytics.incidents — run `make incidents` first.")
    incident_id = str(row[0])

    yield incident_id

    # Teardown: drop any hypotheses the test created for this incident.
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM analytics.rca_hypotheses WHERE incident_id = %s",
            (incident_id,),
        )
    conn.commit()


def _make_hypothesis(rule_id: str, confidence: float) -> Hypothesis:
    return Hypothesis(
        rule_id=rule_id,
        confidence=confidence,
        evidence={
            "rule_snapshot": {
                "name": f"Test rule {rule_id}",
                "likely_cause": "Synthetic test cause",
                "suggested_actions": ["Do a test thing"],
                "evidence_template": None,
            },
            "triggers": [
                {
                    "type": "concurrent_fm_alarm",
                    "alarm_uid": 123,
                    "alarm_type": "S1_LINK_DOWN",
                    "delta_minutes": 2.5,
                }
            ],
        },
    )


def test_persist_inserts_rows_with_ranks(conn, test_incident_id):
    """Rank is assigned by input position (1 = top)."""
    hypotheses = [
        _make_hypothesis("rca_001", 0.9),
        _make_hypothesis("rca_002", 0.6),
        _make_hypothesis("rca_003", 0.4),
    ]

    inserted = persist_hypotheses(test_incident_id, hypotheses, conn)
    assert inserted == 3

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT hypothesis_rank, rule_id, confidence
            FROM analytics.rca_hypotheses
            WHERE incident_id = %s
            ORDER BY hypothesis_rank
            """,
            (test_incident_id,),
        )
        rows = cur.fetchall()

    assert len(rows) == 3
    assert [r[0] for r in rows] == [1, 2, 3]
    assert [r[1] for r in rows] == ["rca_001", "rca_002", "rca_003"]
    assert [float(r[2]) for r in rows] == [0.9, 0.6, 0.4]


def test_persist_evidence_round_trips_through_jsonb(conn, test_incident_id):
    """Dict evidence survives the JSONB round-trip unchanged."""
    original = _make_hypothesis("rca_001", 0.8)
    persist_hypotheses(test_incident_id, [original], conn)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT evidence
            FROM analytics.rca_hypotheses
            WHERE incident_id = %s AND hypothesis_rank = 1
            """,
            (test_incident_id,),
        )
        (stored,) = cur.fetchone()

    assert stored == original.evidence
    assert stored["rule_snapshot"]["name"] == "Test rule rca_001"
    assert stored["triggers"][0]["type"] == "concurrent_fm_alarm"


def test_persist_replaces_existing_hypotheses(conn, test_incident_id):
    """A second persist replaces the first — no leftover rows."""
    first = [
        _make_hypothesis("rca_001", 0.9),
        _make_hypothesis("rca_002", 0.5),
        _make_hypothesis("rca_003", 0.3),
    ]
    persist_hypotheses(test_incident_id, first, conn)

    second = [
        _make_hypothesis("rca_004", 0.8),
        _make_hypothesis("rca_005", 0.4),
    ]
    inserted = persist_hypotheses(test_incident_id, second, conn)
    assert inserted == 2

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rule_id, hypothesis_rank
            FROM analytics.rca_hypotheses
            WHERE incident_id = %s
            ORDER BY hypothesis_rank
            """,
            (test_incident_id,),
        )
        rows = cur.fetchall()

    # Old rule_ids should be gone entirely, not merged.
    rule_ids = {r[0] for r in rows}
    assert rule_ids == {"rca_004", "rca_005"}
    assert [r[1] for r in rows] == [1, 2]


def test_persist_empty_list_clears_existing(conn, test_incident_id):
    """Passing [] removes all hypotheses for the incident."""
    persist_hypotheses(test_incident_id, [_make_hypothesis("rca_001", 0.7)], conn)

    inserted = persist_hypotheses(test_incident_id, [], conn)
    assert inserted == 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM analytics.rca_hypotheses WHERE incident_id = %s",
            (test_incident_id,),
        )
        (count,) = cur.fetchone()

    assert count == 0


def test_persist_is_idempotent(conn, test_incident_id):
    """Same input twice leaves the same final state."""
    hypotheses = [
        _make_hypothesis("rca_001", 0.9),
        _make_hypothesis("rca_002", 0.6),
    ]

    persist_hypotheses(test_incident_id, hypotheses, conn)
    persist_hypotheses(test_incident_id, hypotheses, conn)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rule_id, hypothesis_rank, confidence
            FROM analytics.rca_hypotheses
            WHERE incident_id = %s
            ORDER BY hypothesis_rank
            """,
            (test_incident_id,),
        )
        rows = cur.fetchall()

    assert len(rows) == 2
    assert rows[0][0] == "rca_001"
    assert rows[1][0] == "rca_002"
