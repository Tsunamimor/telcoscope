# DEC-005 — Severity calibration philosophy

## Status

Accepted — 2026-10-19 (Week 4 Day 2 close)

## Context

Each detector produces a numeric score per flagged row. The pipeline
labels every detection with a severity (`info`, `minor`, `major`,
`critical`) by comparing the score against detector-specific thresholds
in `_SEVERITY_THRESHOLDS`.

Two choices need justifying:
1. **How are the thresholds set** — fixed values, percentile of score
   distribution, business rules, something else?
2. **Should both detectors use the same calibration philosophy** —
   given that they play different roles (statistical: broad coverage;
   IF: tighter precision)?

Observed on the Week 4 Day 2 synthetic run after the threshold tune:

| Detector | info | minor | major | critical |
|---|---|---|---|---|
| Statistical | 48.6% | 41.8% | 8.6% | 1.0% |
| Isolation Forest | 74.6% | 15.5% | 8.8% | 1.1% |

The two detectors agree on major and critical fractions (both ~P90 and
~P99 of their own `abs(score)` distributions). They disagree on info —
statistical splits roughly 50/50 info/minor, IF splits roughly 75/25.
That asymmetry is deliberate, and it needs to be documented so a
reviewer doesn't flag it as inconsistency.

## Decision

**Phase 1 — percentile-based calibration against each detector's own
`abs(score)` distribution.** This is the current state for synthetic
data. Thresholds:

| Severity | Statistical | Isolation Forest |
|---|---|---|
| critical | P99 (= 300) | P99 (= 0.093) |
| major | P90 (= 50) | P90 (= 0.059) |
| minor | **P50 (= 7)** | **~P70 (= 0.030)** |

Both detectors share critical = P99 and major = P90 of `abs(score)` so
their performance can be compared like-for-like in
`mart_detector_evaluation`.

Minor thresholds are deliberately **asymmetric** between detectors.
Rationale:

- **Statistical** fires on univariate deviations from a seasonal
  baseline per KPI. Its role is broad coverage — catch anything that
  looks unusual, including long-tail minor degradations an operator
  might want to see even if it's never a critical event. P50 for minor
  means half the persisted detections survive as "at least minor" and
  the other half fall to info. The dashboard sees everything the
  detector thought was worth flagging; the ops team filters.
- **Isolation Forest** uses `contamination=0.02` and already flags only
  the top 2% of multivariate outliers. Its persisted score distribution
  is tighter at the low end. P70 for minor keeps IF's actionable output
  genuinely rare — the info bucket absorbs the low-signal portion of
  IF's flags, so when IF says "minor" it means something.

**Phase 2 (production, deferred) — layer business rules.** Severity
would then combine detector score with cell importance, time of day,
concurrent FM alarms, and recent CM changes. Detector score becomes an
input to severity, not the final verdict.

**Phase 3 (mature operation, deferred) — adaptive calibration.** Rolling-
window percentile recalibration against the trailing 30 days of
production data, re-tuned nightly. Thresholds drift with the network
as sites, software upgrades, and seasonal patterns change the noise
floor.

## Alternatives considered

- **Unified minor = P50 across both detectors.** Rejected: makes IF
  noisier than its `contamination=0.02` role implies. IF already
  flagged only the top 2%; cutting at P50 of that top-2% distribution
  defeats IF's main selling point of precision.
- **Unified minor = P70 across both.** Rejected: makes statistical
  miss its "broad coverage" role. Statistical's value is catching
  long-tail minor-grade real anomalies that IF ignores; raising its
  minor cut to P70 would push ~20% of currently-minor flags down to
  info, which operators would want to see.
- **Fixed absolute thresholds (not percentile-based).** Rejected:
  thresholds would silently drift as data distributions change, or
  as detectors are retrained with new parameters. Percentile-based
  calibration is self-adjusting against the detector's own output,
  which is the right abstraction for v1.
- **Business-rule-first severity (no detector thresholds at all).**
  Deferred to Phase 2. Not viable in Phase 1 because the inputs for
  business rules (cell importance, FM correlation, CM change history)
  don't exist yet.

## Consequences

- Statistical shows ~50% info, IF shows ~75% info. The dashboard will
  look different per method, which is intentional and documented here.
  A reviewer glancing at the severity split should see this ADR as
  the justification.
- Both detectors give identical critical% and major% at the aggregate
  level (both at P99 and P90 of their own distributions), which
  keeps the `mart_detector_evaluation` comparison fair.
- Statistical's minor bucket is denser — operators get a higher
  volume of minor flags to triage. Trade-off: more noise, more real
  coverage.
- The percentile values are tied to the current data distribution.
  When data characteristics change (new vendor, new seasonal pattern,
  new KPI mix), the thresholds need re-measurement. The query in
  CHEATSHEET §5 produces the current P50/P90/P99 on demand.
- Phase 2 and Phase 3 are a documented evolution — the current
  calibration is honest about being Phase 1, not pretending to be
  production-ready severity logic.
- `isolation.py` minor at ~P70 (0.030 vs actual P50 0.016) is a
  conscious choice, not a bug. Backlog item BKL-001 refinement to
  drop minor to P50 would shift IF toward statistical's broader
  coverage, which contradicts the role described in this ADR.
  Resolution: close the BKL-001 refinement sub-action as "intentional
  — see DEC-005".