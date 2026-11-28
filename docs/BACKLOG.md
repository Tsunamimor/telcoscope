# telcoscope — Backlog

> **This is the living backlog.** Items that aren't blocking current work
> but shouldn't be lost. Updated as items are added, worked, or dropped.
> See end for maintenance protocol.

---

## Status

| Field | Value |
|---|---|
| **Version** | v0.5 |
| **Last updated** | 2026-11-27 |
| **Current week** | 5 — Day 2 complete (DEC-006 RCA engine shipped end-to-end on `wk5/day2-rca-engine`, 28 hypotheses firing across 4 rules on real data) |

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

### BKL-007 — Modernise dbt generic test syntax

**Opened:** 2026-10-31 (Week 5 Day 1)
**Priority:** Low — forward-compat, zero behaviour change today
**Area:** `dbt/models/staging/_sources.yml`, `dbt/models/marts/_marts.yml`

**Context.** dbt 1.12 emits `MissingArgumentsPropertyInGenericTestDeprecation`
warnings for every generic test defined with top-level args instead of
nesting them under an `arguments:` key. Current count: 21 occurrences
across sources and marts yml files (`relationships`, `accepted_values`,
`accepted_range`, `unique_combination_of_columns`). Four `relationships:`
entries in `_sources.yml` were already converted in Week 5 Day 1 as
part of BKL-004; the rest remain on the old syntax. Also surfaced
during the BKL-004 rerun: `dim_enb.vendor_id` has a relationships test
pointing at `source('dims', 'dim_vendor')` but `dim_vendor` is not
declared as a source in `_sources.yml` — the test is a silent no-op
today.

**Actions when picked up:**
- Wrap every `accepted_values:`, `accepted_range:`, `relationships:` and
  `unique_combination_of_columns:` block in both yml files under an
  `arguments:` key (same pattern as the 4 relationships fixes already
  landed).
- Register `dim_vendor` as a source under the `dims` namespace in
  `_sources.yml` (or drop the orphan relationships test on
  `dim_enb.vendor_id` if the mart doesn't need it).
- Rerun `dbt test` and confirm `MissingArgumentsPropertyInGenericTestDeprecation`
  count is 0 and no orphan-source warnings remain.
- Low risk — no behaviour change, just syntax modernisation.

---

### BKL-008 — Synth generator should inject correlated RCA scenarios

**Opened:** 2026-11-27 (Week 5 Day 2 close)
**Priority:** Medium — gates meaningful RCA precision/recall evaluation
**Area:** `src/telcoscope/synth/generator.py`, `src/telcoscope/synth/anomalies.py`, `src/telcoscope/rca/rules.yaml`

**Context.** The synth generator today injects anomalies, FM alarms,
and CM changes independently of each other. Result: when the Week 5
Day 2 RCA engine runs across all 7077 incidents, only 28 (0.4%)
produce any hypothesis — rca_003 (10), rca_004 (7), rca_001 (6),
rca_005 (5). In real operator data, RCA fires on 60–80% of incidents
because alarms / CM / KPI behaviour are causally linked to service
degradation. Without that linkage in synth, the RCA engine's
precision/recall is unmeasurable — we can't tell a true-positive
hypothesis from a chance correlation.

Also surfaced during diagnosis: hardware-fault rule `rca_002` has
**zero matches** because the synth vocabulary is `TEMPERATURE_HIGH`
and `VSWR_MINOR`, not the `BOARD_*` / `RRU_*` / `RU_*` prefixes the
rule regex expects. Similarly FM alarm total (436) is ~7× lower than
HLD §7 claims ("~100/day for 100 cells" = ~3000 expected), and CM
changes stop ~1 day before the latest incident (42 total, latest
`2026-08-24`).

**Actions when picked up:**
- Extend the generator with three scenario classes, each labelled in
  `synth_truth` so detector AND RCA precision/recall can both be
  measured against ground truth:
  - **Transport-fault scenario** — inject an `S1_LINK_DOWN` /
    `S1_FAILURE` alarm at major+ severity, then a correlated
    accessibility drop (RRC/ERAB setup SR) on the same eNB cluster
    within 2–15 minutes.
  - **Hardware-fault scenario** — inject a `BOARD_FAULT` /
    `RRU_FAILURE` / `RU_TEMPERATURE` alarm at minor+ severity, then
    an availability drop on the single affected cell within ~0 min.
  - **Config-regression scenario** — inject a CM change on a
    parameter known to affect a specific KPI, then a KPI drop on
    the same cell within 60 minutes.
- Widen hardware alarm vocabulary (`BOARD_*`, `RRU_*`, `RU_*`) so
  `rca_002` has matching inputs.
- Raise FM alarm volume closer to the HLD §7 target (~100/day/100
  cells).
- Extend CM change generation to cover the full synthetic window.
- Target: after regeneration, RCA engine fires on >= 30% of
  non-info incidents, and `mart_detector_evaluation` gains an RCA
  equivalent (`mart_rca_evaluation`) comparing the ranked
  hypotheses against the injected scenario labels.

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

### CLS-005 — cell_id type harmonisation (was BKL-004)

Closed 2026-10-31 (Week 5 Day 1). `cell_id` was `TEXT` in
`analytics.anomalies` and `analytics.incidents` but `BIGINT` everywhere
else, forcing an explicit `::text` cast on every join against KPI marts
(surfaced in `mart_incidents_timeline` on Week 4 Day 3). Alembic
migration `cce4fb944f55_harmonise_cell_id_to_bigint_on_analytics_tables.py`
alters both columns to `BIGINT`, drops/recreates the dependent dbt
marts (`mart_detector_evaluation` as a table, `mart_incidents_timeline`
as a view) and the `uq_incidents_cell_ts_start` unique index. The
`::text` casts in `mart_incidents_timeline.sql` were removed, the
`Incident` dataclass in `grouper.py` now uses `cell_id: int`, grouper
tests were updated to pass int cell_ids (11/11 pass, 100% coverage),
and two new `relationships` tests were added in `_sources.yml`
guarding `analytics.anomalies.cell_id` and `analytics.incidents.cell_id`
against `dim_cell.cell_id` — both pass, locking the type in place.
Gotcha found during rollout: `mart_detector_evaluation` is materialised
as a dbt **table**, not a view, so `DROP VIEW IF EXISTS` fails on it —
the migration uses `DROP TABLE IF EXISTS` for that one and `DROP VIEW
IF EXISTS` for `mart_incidents_timeline`. Follow-on backlog item
**BKL-007** opened for the project-wide dbt generic test syntax
modernisation that surfaced during the same work.

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
