"""Persistence for RCA hypotheses.

Writes a list of ``Hypothesis`` objects produced by ``rca.engine``
into ``analytics.rca_hypotheses``, keyed on
``(incident_id, hypothesis_rank)``.

Semantics: one call **replaces** all hypotheses for the incident.
Rank is assigned by position in the input list (1 = top), so the
caller is expected to have sorted by confidence first —
``rca.engine.evaluate_incident`` already does that.

DELETE + INSERT inside one transaction means a re-run with fewer
matches won't leave stale high-rank rows behind — the
``rca_hypotheses`` set for an incident is always a clean snapshot of
the latest engine output. The FK's ON DELETE CASCADE on
``incidents`` also means an incident being deleted takes its
hypotheses with it, so this module never needs to clean up after an
upstream delete.
"""

from __future__ import annotations

from uuid import UUID

from loguru import logger
from psycopg import Connection
from psycopg.types.json import Jsonb

from telcoscope.rca.engine import Hypothesis

_INSERT_SQL = """
    INSERT INTO analytics.rca_hypotheses (
        incident_id,
        hypothesis_rank,
        rule_id,
        confidence,
        evidence
    ) VALUES (
        %(incident_id)s,
        %(hypothesis_rank)s,
        %(rule_id)s,
        %(confidence)s,
        %(evidence)s
    )
"""

_DELETE_SQL = """
    DELETE FROM analytics.rca_hypotheses WHERE incident_id = %s
"""


def persist_hypotheses(
    incident_id: str | UUID,
    hypotheses: list[Hypothesis],
    conn: Connection,
) -> int:
    """Replace all hypotheses for one incident with the new list.

    Deletes any existing rows for ``incident_id`` and inserts the
    provided hypotheses with ``hypothesis_rank`` assigned by input
    position (1 = highest confidence). The caller is expected to
    pass a confidence-sorted list — ``rca.engine.evaluate_incident``
    already does that. Passing an empty list clears all hypotheses
    for the incident.

    All DB work happens in a single transaction (commit on return).
    Returns the number of rows inserted.
    """
    inc_id = str(incident_id)

    with conn.cursor() as cur:
        cur.execute(_DELETE_SQL, (inc_id,))
        deleted = cur.rowcount

        if hypotheses:
            cur.executemany(
                _INSERT_SQL,
                [
                    {
                        "incident_id": inc_id,
                        "hypothesis_rank": rank,
                        "rule_id": h.rule_id,
                        "confidence": h.confidence,
                        "evidence": Jsonb(h.evidence),
                    }
                    for rank, h in enumerate(hypotheses, start=1)
                ],
            )

    conn.commit()

    inserted = len(hypotheses)
    logger.info(
        "Persisted RCA hypotheses for incident {}: {} deleted, {} inserted",
        inc_id,
        deleted,
        inserted,
    )
    return inserted
