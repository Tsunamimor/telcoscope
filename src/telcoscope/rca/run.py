"""RCA pipeline orchestrator — entry point for ``make rca``.

Loads the rule library, iterates every non-trivial incident in
``analytics.incidents``, evaluates it against the rule library, and
persists the resulting top-N hypotheses into
``analytics.rca_hypotheses``.

Options (env vars):

- ``RCA_RULES_PATH``: path to a ``rules.yaml``. Defaults to the one
  shipped with the package (``src/telcoscope/rca/rules.yaml``).
- ``RCA_TOP_N``: hypotheses to keep per incident (default 5, per
  DEC-006 §2.4).
- ``RCA_INCIDENT_SEVERITY_FILTER``: comma-separated severities to
  process (default ``minor,major,critical`` — skips ``info``).
- ``RCA_MAX_INCIDENTS``: cap on incidents processed in one run
  (default 0 = unlimited). Useful for staged roll-out on a large
  backlog.

Safe to re-run: ``persist_hypotheses`` is a full-replacement write
per incident, so a second ``make rca`` with the same rules leaves
the DB in the same state.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from loguru import logger

from telcoscope.config import settings
from telcoscope.rca.engine import DEFAULT_TOP_N, evaluate_incident, load_rules
from telcoscope.rca.persistence import persist_hypotheses

_INCIDENT_QUERY = """
    SELECT incident_id, cell_id, ts_start, ts_end, severity
    FROM analytics.incidents
    WHERE severity = ANY(%(severities)s)
    ORDER BY ts_start DESC
    {limit_clause}
"""


def main() -> int:
    """Run the RCA pipeline end-to-end. Returns a process exit code."""
    rules_path_env = os.getenv("RCA_RULES_PATH", "").strip()
    rules_path: Path | None = Path(rules_path_env) if rules_path_env else None
    top_n = int(os.getenv("RCA_TOP_N", str(DEFAULT_TOP_N)))
    severities = [
        s.strip()
        for s in os.getenv("RCA_INCIDENT_SEVERITY_FILTER", "minor,major,critical").split(",")
        if s.strip()
    ]
    max_incidents = int(os.getenv("RCA_MAX_INCIDENTS", "0"))

    library = load_rules(rules_path) if rules_path else load_rules()

    dsn = settings.postgres_url.replace("+psycopg", "")
    limit_clause = f"LIMIT {max_incidents}" if max_incidents > 0 else ""
    query = _INCIDENT_QUERY.format(limit_clause=limit_clause)

    processed = 0
    total_hypotheses = 0

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"severities": severities})
            incidents = cur.fetchall()

        logger.info(
            "RCA pipeline starting: {} incidents in scope (severities={}, limit={})",
            len(incidents),
            severities,
            max_incidents or "unlimited",
        )

        for row in incidents:
            incident_id, cell_id, ts_start, ts_end, severity = row
            incident = {
                "incident_id": str(incident_id),
                "cell_id": cell_id,
                "ts_start": ts_start,
                "ts_end": ts_end,
                "severity": severity,
            }

            hypotheses = evaluate_incident(incident, library, conn, top_n=top_n)
            persist_hypotheses(incident_id, hypotheses, conn)

            processed += 1
            total_hypotheses += len(hypotheses)

            if processed % 100 == 0:
                logger.info(
                    "Progress: {}/{} incidents, {} hypotheses written so far",
                    processed,
                    len(incidents),
                    total_hypotheses,
                )

    logger.info(
        "RCA pipeline complete: {} incidents processed, {} hypotheses written",
        processed,
        total_hypotheses,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
