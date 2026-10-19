# DEC-004 — Incident grouping model

## Status

Accepted — 2026-10-13 (Week 4 Day 1)

## Context

Week 3 produced per-row detections in `analytics.anomalies`: one row per
fired flag per cell per hour per KPI per method. That's dense and noisy —
nobody operates a NOC off raw rows. Operators think in incidents: a
time-bounded cluster of related detections on the same site.

Week 4 needs a grouping model that turns raw detections into actionable
incidents. The model has to answer four questions:

1. What counts as "the same incident"?
2. What severity does the incident inherit from its constituent
   detections?
3. When does an incident close?
4. How do we stay idempotent when the grouper reruns?

## Decision

**Grouping key.** Group detections by `(cell_id, time proximity)`
regardless of which method flagged them. Multi-method agreement on the
same cell-time cluster raises confidence; it does not create duplicate
incidents.

**Silence threshold.** 2 hours. If no further detection fires on the
cell within 2 hours of the last detection in a group, the incident
closes at that last detection's timestamp. Otherwise the group extends.

**Severity rollup.** `severity = max(severity_rank)` over the group's
detections. One critical detection in a group of ten → incident is
critical. Worst-case drives on-call priority.

**Lifecycle.** `open` → `resolved`. Auto-resolution happens when no
detection fires on the cell for 2 hours (same threshold as the group-
splitting rule).

**Idempotency.** `analytics.incidents` has a UNIQUE index on
`(cell_id, ts_start)`. The grouper upserts via `ON CONFLICT (...) DO
UPDATE`, so rerunning on the same anomaly set produces the same incident
set.

**Info filter.** Detections with `severity = 'info'` are excluded from
grouping at the SQL layer in `run.py`. Info-level flags are preserved in
`analytics.anomalies` for inspection but don't form incidents.

Detailed schema and column list in HLD §7.

## Alternatives considered

- **Per-method incidents** (statistical and IF kept separate). Rejected:
  real-world events fire on both methods simultaneously; two methods on
  the same cell at the same time are one event, not two. Would also
  double-notify downstream consumers in Week 4 Day 4.
- **Fixed-time windows** (hourly, 4-hourly bucketing). Rejected: splits
  a sustained 3-hour outage into three artificial incidents, and
  compresses two unrelated 10-minute blips into one.
- **Topology-aware grouping** (sector-level, neighbour-cell correlation).
  Deferred to post-Week 4. A cascading failure across neighbour cells
  will currently produce one incident per cell; acceptable for v1
  because the sector grouping is a separate roll-up that can layer
  over this one without changing the primary incident model.
- **Weighted or modal severity rollup** instead of max. Rejected: in
  ops, "critical anywhere in the window" demands critical response;
  a weighted average would soften a legitimate critical event just
  because it was surrounded by minors.
- **Keep info in grouping**. Rejected: info-level detections aren't
  actionable by definition; letting them extend an incident's window
  would stretch resolution times without adding operational value.

## Consequences

- One incident per real-world event, regardless of how many detectors
  or KPIs tripped during it.
- Simple to implement — a single sorted walk with a gap check. Pure
  function, trivially testable.
- Max-severity rollup matches the ops escalation model directly.
- 2h threshold is a heuristic derived from NOC shift cadence; it will
  need recalibration against real incident data when telcoscope ingests
  live PM feeds. Flagged in HLD §11.
- No sector-level correlation — a cascading failure appears as multiple
  parallel incidents. Acceptable for v1; sector grouping is a separate
  future artifact that joins this incidents table to a topology
  dimension.
- Idempotency depends on the UNIQUE index on `(cell_id, ts_start)`;
  the schema migration enforces this, so the grouper can safely be
  rerun on cron or via `make incidents` without doubling.
- Observed compression on synthetic data is ~1.6×–2.1× (dependent on
  severity thresholds and whether info is filtered). Real data is
  expected to compress more because real cell outages degrade over
  many hours before intervention.