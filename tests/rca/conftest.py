"""Shared setup for RCA tests.

The DB-driven smoke / integration tests in this directory all read
from ``analytics.incidents``. In environments where that table
doesn't exist (CI, a fresh dev machine before migrations are run),
the first SELECT puts a module-scoped psycopg connection into
INERROR state and cascades failures through every DB-dependent
test in the module.

This conftest probes ``analytics.incidents`` at collection time and
marks the 10 DB-dependent tests to skip with a clear reason if the
table isn't populated. Pure-unit tests (rule-loading, monkeypatched
engine logic, the KPI allow-list guard) run unchanged.
"""

from __future__ import annotations

import psycopg
import pytest

from telcoscope.config import settings


def _analytics_incidents_available() -> bool:
    """Return True if analytics.incidents exists and has >= 1 row."""
    dsn = settings.postgres_url.replace("+psycopg", "")
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM analytics.incidents LIMIT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


_SKIP_REASON = (
    "analytics.incidents not populated in this database — run "
    "`alembic upgrade head && make seed && make detect && make incidents` "
    "before the RCA integration tests"
)

_DB_TEST_NAMES = frozenset(
    {
        # test_resolvers_smoke.py
        "test_alarm_resolver_smoke",
        "test_cm_change_resolver_smoke",
        "test_neighbour_resolver_smoke",
        "test_kpi_pattern_resolver_smoke",
        # test_engine.py
        "test_evaluate_incident_against_real_db",
        # test_persistence.py
        "test_persist_inserts_rows_with_ranks",
        "test_persist_evidence_round_trips_through_jsonb",
        "test_persist_replaces_existing_hypotheses",
        "test_persist_empty_list_clears_existing",
        "test_persist_is_idempotent",
    }
)


def pytest_collection_modifyitems(config, items):
    """Skip DB-driven RCA tests when analytics.incidents isn't populated."""
    if _analytics_incidents_available():
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if item.name in _DB_TEST_NAMES:
            item.add_marker(skip)
