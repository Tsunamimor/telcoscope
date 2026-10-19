# DEC-003 — Interface-first detector pattern

## Status

Accepted — 2026-10-05 (Week 3)

## Context

Week 3 introduces anomaly detection. The portfolio story needs more than one
detector: a statistical method (seasonal modified z-score) and an ML method
(Isolation Forest). The two give different signal — statistical catches
univariate deviations, IF catches multivariate patterns — and the project's
evaluation story (precision/recall/F1 against ground-truth injections)
depends on being able to compare them like-for-like.

Future weeks will likely add more detectors (a transformer-based variant,
an LLM-assisted one, business-rules). Each needs to plug into the same
persistence, evaluation, and dashboard layers without rewrites.

## Decision

Define a single abstract `Detector` base class in
`src/telcoscope/detect/base.py` with one required method:

```python
def detect(self, df: pl.DataFrame) -> pl.DataFrame
```

Input is the KPI mart (`mart_kpi_cell_hourly`). Output is a Polars
DataFrame matching `DETECTION_SCHEMA`. Each concrete subclass
(`StatisticalDetector`, `IsolationForestDetector`) implements `detect()`
and owns its own `_SEVERITY_THRESHOLDS` dict.

Persistence lives separately in `src/telcoscope/detect/persistence.py`
as a module-level function `persist_detections(df, method)` that takes
any detector's output DataFrame plus a method tag and writes to
`analytics.anomalies`.

Orchestration lives in `src/telcoscope/detect/run.py`: it reads the KPI
mart once, invokes each detector, hands the output to persistence.

## Alternatives considered

- **Separate modules, no shared interface.** Each detector would have
  its own call signature and persistence code. Rejected: evaluation
  becomes ad-hoc, adding a third detector means touching three places,
  and there's no single schema contract.
- **Pipeline framework (sklearn-style Pipeline, prefect, etc.).**
  Rejected: overkill for 2–3 detectors run in sequence. Framework
  dependency cost outweighs the structuring benefit until we hit 5+
  detectors or need DAG scheduling.
- **Dataclass-only, no abstract class.** Considered: lighter weight,
  no `ABC`-style ceremony. Rejected because an abstract class with a
  `@abstractmethod` lets mypy catch missing implementations at type-
  check time; a dataclass would only surface the failure at runtime.
- **Each detector owns its persistence call.** Rejected: duplicates
  the Postgres connection boilerplate across every detector file and
  couples scoring logic to I/O.

## Consequences

- Adding a third detector is a new file (`src/telcoscope/detect/<name>.py`)
  that subclasses `Detector` and sets `_SEVERITY_THRESHOLDS`. No changes
  to persistence, evaluation, orchestration, or the dashboard.
- `mart_detector_evaluation` can compare every method uniformly on
  precision/recall/F1 — the dbt join keys on `method` plus `(cell_id,
  ts)` to the ground-truth table.
- Separation of concerns is clear: detector = scoring, persistence =
  DB writes, orchestrator = coordination. Each is independently
  testable.
- The DataFrame schema contract is implicit — detectors must return
  columns matching `DETECTION_SCHEMA` or persistence fails at runtime.
  An explicit Pydantic model could tighten this if the schema contract
  gets abused. Backlogged as low priority.
- Per-subclass `_SEVERITY_THRESHOLDS` is deliberate — the two detectors
  have incomparable score scales (statistical: 0 to thousands; IF:
  0 to 0.15). A unified threshold dict in `base.py` would require
  both to project onto a common scale first, which neither does.
  (A shared `_score_to_severity` method on the base class is a
  separate, additive refactor — see BKL-003.)