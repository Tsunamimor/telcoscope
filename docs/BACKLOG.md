# telcoscope — Backlog

> **This is the living backlog.** Items that aren't blocking current work
> but shouldn't be lost. Updated as items are added, worked, or dropped.
> See end for maintenance protocol.

---

## Status

| Field | Value |
|---|---|
| **Version** | v0.3 |
| **Last updated** | 2026-10-28 |
| **Current week** | 4 — Day 4 functionally complete (notifier working against Synology webhook-tester) |

---

## 1. Open items

### BKL-002 — Detect persistence idempotency

**Opened:** 2026-10-13 (Week 4 Day 2)
**Priority:** Medium — gotcha, not blocking
**Area:** `src/telcoscope/detect/persistence.py`

**Context.** `persist_detections` uses plain INSERT, so running
`make detect` twice doubles `analytics.anomalies`. Surfaced during Day 2
when the table showed 44628 rows after two runs of a 22314-row detect.
Workaround today is `TRUNCATE analytics.anomalies` before rerunning;
longer-term the detect module should match the upsert pattern used by
`incidents/persistence.py`.

**Actions when picked up:**
- Add an Alembic migration creating a UNIQUE index on
  `(ts, cell_id, kpi_name, method)` in `analytics.anomalies`.
- Rewrite `persist_detections` to use `ON CONFLICT (...) DO UPDATE`
  mirroring the shape in `incidents/persistence.py`.
- Add a smoke test that double-runs detect and asserts the row count is
  stable across runs.
- Remove the TRUNCATE workaround from any local dev notes.

---

### BKL-003 — Move `_score_to_severity` to `base.py`

**Opened:** 2026-10-08 (Week 3)
**Priority:** Low — cosmetic refactor
**Area:** `src/telcoscope/detect/base.py`

**Context.** `_score_to_severity` is implemented identically in both
`statistical.py` and `isolation.py`. The `_SEVERITY_THRESHOLDS` dict is
correctly per-subclass (different score scales), but the comparison
method is boilerplate.

**Actions when picked up:**
- Add `_score_to_severity(self, score)` to the `Detector` abstract base,
  reading from `self._SEVERITY_THRESHOLDS`.
- Mark `_SEVERITY_THRESHOLDS` as the ABC's required class attribute (type
  hint, no default).
- Delete the duplicated method from both subclasses.
- No behaviour change expected — covered by the existing detector
  smoke tests.

---

### BKL-004 — Harmonise `cell_id` type across `analytics` schema

**Opened:** 2026-10-20 (Week 4 Day 3)
**Priority:** Low — cosmetic + minor performance
**Area:** `src/telcoscope/db` + dbt marts that join

**Context.** `cell_id` is `TEXT` in `analytics.anomalies` and
`analytics.incidents` but `BIGINT` everywhere else in the pipeline
(`dim_cell`, `raw.pm_measurements`, `dbt_dev_marts.mart_kpi_cell_hourly`).
Every join against KPI marts needs an explicit `::text` cast — surfaced
in Week 4 Day 3 when `mart_incidents_timeline` failed with
`operator does not exist: bigint = text`. Current workaround is to cast
inside the mart SQL.

**Actions when picked up:**
- Alembic migration altering `cell_id` from `TEXT` → `BIGINT` on
  `analytics.anomalies` and `analytics.incidents`.
- The UNIQUE index on `analytics.incidents(cell_id, ts_start)` needs
  drop/recreate because the key column type is changing.
- Update `incidents/grouper.py` to emit `int` instead of `str` cell_ids
  (currently reads them as text out of psycopg).
- Remove the `::text` casts from `mart_incidents_timeline.sql` once the
  types match.
- Add a dbt relationship test on `analytics.incidents.cell_id → dim_cell.cell_id`
  that only works once both sides are the same type.

---

### BKL-005 — Highlight dual-method confirmed incidents in Grafana

**Opened:** 2026-10-21 (Week 4 Day 3)
**Priority:** Low — dashboard polish
**Area:** `grafana/dashboards/incidents_ops.json`

**Context.** When an incident has `methods = {statistical, isolation_forest}`
both detectors agreed, which is a stronger signal than either alone
(see HLD §10.2 and DEC-003). The current incident table doesn't visually
distinguish single-method from dual-method incidents, so operators lose
that confidence signal when triaging. A field override on the `methods`
column — different cell colour when both detectors are present — would
make dual-confirmed incidents jump out at a glance.

**Actions when picked up:**
- On the "Incident table (last 50)" panel, add a field override on
  `methods` column.
- Cell type: coloured background; value mapping or regex match for
  rows containing both `statistical` AND `isolation_forest`.
- Pick a colour distinct from the severity palette so the two signals
  (severity × confidence) read independently.
- Add a one-line note in the panel description: "Methods coloured when
  both detectors fired on the same incident".
- Mirror on the "Incident timeline" if it shows per-incident bars.

---

### BKL-006 — Notifier should verify the webhook endpoint, not just trust 2xx

**Opened:** 2026-10-28 (Week 4 Day 4)
**Priority:** Low — silent-failure guard
**Area:** `src/telcoscope/incidents/notifier.py` + `run.py`

**Context.** `notify()` currently treats any 2xx response as success and
marks `notified_at`. Catch-all webhook testers (webhook.site,
tarampampam/webhook-tester, and most mock servers) return `200 "Hello,
world!"` to **any** path — including wrong UUIDs. Surfaced in Week 4
Day 4 when a typo-ed `INCIDENT_WEBHOOK_URL` (placeholder `abc123def456`
rather than the real session UUID) caused the pipeline to report
`7077 sent, 0 skipped` while every payload went into the void and
nothing appeared on the Synology webhook-tester UI. The DB state was
corrupted — all 7077 incidents marked notified — and had to be reset
with `UPDATE analytics.incidents SET notified_at = NULL`.

**Actions when picked up:**
- Add a startup self-check in `run.py`: before draining, POST a sentinel
  payload (e.g. `{"ping": true, "sentinel": "<uuid>"}`) and verify the
  response body or headers contain something only the real endpoint
  would echo (webhook-tester reflects the request ID in the response).
- Alternative: for internal endpoints, call a known health route
  (`/healthz`, `/`) that returns something distinctive before trusting
  the webhook path.
- If the self-check fails, exit before touching `notified_at` — fail
  loudly rather than silently mark 7000 incidents as sent.
- Log a one-line reminder when `INCIDENT_WEBHOOK_URL` matches common
  known-bad patterns (contains `abc123`, `example.com`,
  `your-uuid-here`, etc.) — defence against copying placeholder values
  from docs.

---

## 2. Recently closed

### CLS-001 — Alembic migration path corrected

Closed 2026-10-12 (Week 4 Day 1). The Week 4 guide had said migrations live
at `src/telcoscope/db/alembic/versions/`; actual path is
`db/migrations/versions/` with `alembic.ini` at the repo root. Cheatsheet
and Week 4 guide updated.

### CLS-002 — Container name convention

Closed 2026-10-12. Discovered during psql verify that container names are
`telcoscope-postgres`, `telcoscope-grafana`, `telcoscope-adminer` (no `-1`
suffix) because `docker-compose.yml` pins them explicitly via
`container_name:`. Cheatsheet updated.

### CLS-003 — Interactive psql on Git Bash

Closed 2026-10-12. `docker exec -it` fails on Git Bash with "cannot attach
stdin to a TTY-enabled container" because MINGW64 doesn't present stdin
as a real TTY. Fix: use `winpty docker exec -it ...` for interactive, or
drop `-it` entirely for `-c` / heredoc / pipe. Cheatsheet §2.6 documents
this.

### CLS-004 — Severity threshold reconciliation (was BKL-001)

Closed 2026-10-19 (Week 4 Day 2 close). Root cause was that
`wk3/severity-threshold-tune` branch had never been merged — the Day 2
branch was still running pre-tune thresholds (3.5/7/10 and
0.05/0.15/0.30). After merging that branch and rebasing, statistical
distribution flipped to a textbook ~50% minor / ~40% major / ~1%
critical. IF's wider info bucket (~75%) is now documented as
intentional in **DEC-005** — IF deliberately uses a tighter minor
threshold to preserve its precision role, not an oversight to be fixed.

---

## 3. Maintenance protocol

**When to open an item.** Something came up in-flight that isn't blocking
current work but shouldn't be forgotten: a workaround that needs to
become a proper fix, a design decision deferred, a known bug to triage
later.

**Format.** `BKL-NNN — Short title`, status, priority, area, context (why
it matters), actions when picked up. One screen per item max. If it needs
more, link out to an HLD section or an ADR.

**When to close.** Move the item to §2 "Recently closed" with a one-line
summary. Prune §2 to the most recent 10 entries during HLD version bumps.

**Priority rough guide:**
- **High** — correctness bug, security issue, data loss risk.
- **Medium** — ergonomics problem, gotcha that catches you more than once,
  foreseeable future blocker.
- **Low** — cosmetic refactor, nice-to-have, speculative.

Nothing in this doc should imply a deadline — if a backlog item has one,
it's not a backlog item, it's a task.
