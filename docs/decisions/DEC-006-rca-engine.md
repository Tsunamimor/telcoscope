# DEC-006 — RCA engine: rules-first, YAML-driven, per-incident

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-31 |
| **Week** | 5 — Day 2 |
| **Supersedes** | — |
| **Superseded by** | — |
| **Related** | DEC-003 (detector interface), DEC-004 (incidents grouping), DEC-005 (severity calibration), HLD §6 (RCA component), HLD §5.4 (YAML-driven rule library) |

---

## 1. Context

Week 4 shipped the `analytics.incidents` table — grouped anomalies with
severity, methods, dominant KPI, time span. That answers the *what* and
*where* of a network event, but a NOC operator looking at an incident
still has to answer the *why* themselves: was it a transport fault, a
load spike, a configuration change that just landed, a neighbour-cell
outage pulling traffic? Today the operator reconciles the incident
against fault alarms, CM changes, and neighbour-cell state manually.

Root cause analysis — proposing ranked, evidence-backed hypotheses for
*why* an incident is happening — is the component that turns incidents
from a dashboard row into something a L1 operator can triage without
escalating. It is also the component that most clearly distinguishes
a telecom-literate observability platform from a generic one: the
hypotheses are built from telco-specific signals (concurrent FM
alarms, recent CM changes on the same cell, correlated anomalies on
sector-adjacent cells), using telco-specific correlation windows and
causal rules that only make sense in a RAN context.

Week 5 Day 2 begins building this component. Before any code, we need
to pin the shape it takes — because the choice between a rules-based
engine, a learned classifier, and an LLM narrator has downstream
consequences for schema, test strategy, operator UX, cost, and the
component's believability to a telecoms hiring audience.

---

## 2. Decision

**The RCA engine is a rules-first, YAML-driven, per-incident retriever
that produces ranked hypotheses with evidence.**

Five concrete commitments:

### 2.1 Rules-first, not ML or LLM

The engine evaluates a declarative rule library against each incident.
No classifier, no clustering, no LLM-in-the-loop at the hypothesis-
generation stage. The LLM narrator (Week 5 Day 4) is a separate
component that *describes* the hypotheses in prose, downstream of the
engine — it is not the engine itself.

### 2.2 YAML schema for the rule library

Rules live in `rca/rules/*.yml`, one file per thematic bundle
(`transport.yml`, `load.yml`, `config_changes.yml`, `neighbour.yml`).
Each rule is a declarative pattern plus a confidence score and an
explanation template. Rules load at engine startup and are validated
against a pydantic schema in `src/telcoscope/rca/schema.py`.

### 2.3 Per-incident evaluation, not per-anomaly

The engine takes an `Incident` row (already grouped by Week 4's
grouper) and asks "what caused this?" — it does not re-ask "is this
anomalous?" That question was already answered upstream. Scope
discipline matters: an engine that re-evaluates anomaly status drifts
back into detection and ends up competing with the detectors.

### 2.4 Multiple hypotheses, ranked by confidence

The engine behaves like a retriever, not a classifier. For each
incident it emits the top N (default 5) matching rules, each with a
numeric confidence score computed from the rule's base weight × the
evidence match strength. Operators see the ranked list; they are the
classifier.

### 2.5 Persistence in `analytics.rca_hypotheses`

A new table, one row per (incident_id, hypothesis_rank), with:

- `incident_id` BIGINT NOT NULL REFERENCES `analytics.incidents(incident_id)` ON DELETE CASCADE
- `hypothesis_rank` INT NOT NULL (1 = top)
- `rule_id` TEXT NOT NULL — references the loaded rule's `id` field
- `confidence` NUMERIC(5,4) NOT NULL — in [0, 1]
- `evidence` JSONB NOT NULL — rule-specific supporting facts
- `generated_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()
- UNIQUE (incident_id, hypothesis_rank)

Alembic migration lands this as part of Week 5 Day 2 Step 1.

---

## 3. Rule schema (sketch)

Shape pinned here to make the ADR concrete; full pydantic class lives
in `rca/schema.py`.

```yaml
id: transport_fault_concurrent_s1
title: "Transport fault on same cell within correlation window"
weight: 0.85
triggers:
  - type: concurrent_fm_alarm
    alarm_class: TRANSPORT
    correlation_window_minutes: 15
    cell_scope: same_cell
evidence_template: |
  FM alarm {{ alarm.alarm_uid }} ({{ alarm.alarm_class }}) raised at
  {{ alarm.raised_at }} on cell {{ incident.cell_id }}, within
  {{ delta_minutes }} minutes of incident start.
```

**Trigger types** (fixed, pydantic-enum):

- `concurrent_fm_alarm` — matches rows in `raw.fm_alarms` within a
  window on the same or related cell
- `recent_cm_change` — matches rows in `raw.cm_changes` within a
  window on the same cell
- `neighbour_cell_anomaly` — matches `analytics.anomalies` on a cell
  known to be sector-adjacent (via `dim_cell` enb grouping as a v1
  proxy for a true neighbour graph)
- `kpi_pattern` — matches a specific KPI drop/spike signature on the
  incident's cell at the incident's start time

**Confidence calculation.** `confidence = rule.weight * match_strength`
where `match_strength ∈ [0, 1]` is the trigger-specific strength
(e.g. temporal proximity for FM/CM, correlation strength for
neighbours). Both components clipped to [0, 1] and the product
clipped again, so confidence is always a well-defined probability-ish
value in [0, 1].

---

## 4. Alternatives considered

### 4.1 Rule learning via decision tree

**The pitch.** Train a decision tree on historical incidents labelled
by resolved root cause, let it propose RCA automatically.

**Rejected because:**

- **No training labels.** `synth_truth` labels anomalies as injected
  or not — it does not label *causes*. Building a labelled cause
  dataset means hand-annotating thousands of synthetic incidents, or
  waiting for real operator-labelled data that doesn't exist in this
  project.
- **Rules are the industry baseline.** Real NOC platforms
  (Netcool/Impact, HP OpenView, IBM Tivoli) run on rules. An ML-first
  pitch is a weaker signal than a rules-first one that *acknowledges*
  the ML extension — see §5.3 Exit criteria.
- **Explainability.** Operators triaging a 3am outage need to know
  *why* the system suggested a cause. A rule carries its own
  justification; a tree node does not without SHAP or similar
  machinery.

### 4.2 LLM-based RCA

**The pitch.** Pass each incident's data to Claude and ask it to
propose root causes.

**Rejected because:**

- **Reproducibility.** The same incident must produce the same ranked
  hypotheses on every run for operator trust. LLM output varies at
  temperature > 0; at temperature = 0 the dependency on model
  version still breaks reproducibility across months.
- **Cost non-trivial at operator scale.** 7000+ incidents per 30-day
  synthetic window × an API round-trip each is ~$0.70-$7 per
  pipeline run depending on model. Real operator scale is 10-100×
  higher. Rules are free at runtime.
- **Overlap with the narrator.** Week 5 Day 4 already uses the LLM
  to turn structured hypotheses into prose. Having the LLM also
  *generate* the hypotheses collapses two distinct responsibilities
  into one, and means every narrator change retrains RCA.
- **Portfolio-signal consideration.** An LLM-based RCA is a nice
  demo, but it hides the telecom-specific knowledge that makes this
  project credible to RAN hiring managers. The rule library *is*
  the IP — "Paddy knows a transport alarm within 15 minutes of an
  accessibility drop on the same cell is almost certainly cause,
  but 15 minutes on a neighbour cell is weak evidence". That gets
  encoded explicitly in YAML; an LLM would absorb it and hide it.

### 4.3 Hard-coded Python rule logic

**The pitch.** Write RCA rules as Python functions in `rca/rules.py`.

**Rejected because:**

- Rules change more often than code should. YAML in git lets a
  network engineer propose a rule via PR without touching Python.
- Rule bundling by theme (transport, load, config) is clearer in
  separate YAML files than in branches of a Python module.
- See HLD §5.4 — this was the architectural pillar decision taken
  in Week 1.

---

## 5. Consequences

### 5.1 Positive

- **Operator-trusted output.** Every hypothesis is traceable to a
  named rule with declared weight and a human-readable template.
  No "the model said so" moments.
- **Reviewer-friendly rule history.** Rule changes land as git diffs
  on YAML — the entire reasoning history of the rule library is
  readable in `git log docs/decisions/ rca/rules/`.
- **Independent extension axes.** Adding a new trigger type is a
  pydantic enum entry + a resolver function. Adding a new rule is a
  YAML entry. Adding a new RCA target table (e.g. core-network
  incidents, not just RAN) is a new table — rules and triggers reuse.
- **Testability.** Each rule can be unit-tested against synthetic
  (incident, raw-signal) fixtures. Precision/recall per rule becomes
  a tracked metric, analogous to detector precision in Week 3.
- **Portfolio clarity.** The engine's cleverness lives in the YAML
  library's domain content, which is where the telecom experience is
  demonstrable. The Python engine itself is boring plumbing —
  deliberately so.

### 5.2 Negative

- **Rule-library coverage is the ceiling.** Any incident whose cause
  is not pattern-matched by a rule gets zero hypotheses. Operators
  see "no RCA available" rather than a confident wrong guess, which
  is probably the right failure mode but needs to be explicit in
  the Grafana presentation.
- **Rule drift risk.** As the library grows, overlapping rules can
  produce duplicate hypotheses with slightly different wording. Need
  a de-duplication pass in the ranker (planned: cluster by trigger
  type + evidence overlap, surface the highest-weight representative).
- **Static weights.** The confidence scores are human-assigned, not
  learned. Will miscalibrate as the library grows. See §5.3.

### 5.3 Exit criteria for revisiting

A rules-first engine is correct for v1 and remains correct until the
library's limits become visible. The ADR is reopened when either of
these triggers:

- **Scale trigger.** The rule library grows past ~40 entries and
  manual review shows >20% of produced incidents matching no rule.
  At that point, rule-learning becomes attractive: there is enough
  labelled history to train on and enough blind spots to warrant it.
- **Shadow-usage trigger.** The Week 5 narrator consistently
  rediscovers causal patterns the rule library does not encode (e.g.
  the LLM narration repeatedly cites "neighbour cell X alarmed 20
  minutes before" when no rule captures that). That is the LLM doing
  RCA in prose; the rational response is to formalise the pattern as
  a rule or, if the patterns are too varied to encode, promote the
  LLM to a secondary RCA path with explicit cost gates.

Neither trigger is expected within the Week 5–8 project arc. The
exit criteria exist to prevent the rules-first choice from becoming
institutionally sticky past its useful life.

---

## 6. Implementation plan

Deferred to the Week 5 Day 2 guide (`weeks/wk5-guide.md` §2.2
onwards). Headline steps:

1. Alembic migration adds `analytics.rca_hypotheses` per §2.5
2. `src/telcoscope/rca/schema.py` — pydantic rule model
3. `src/telcoscope/rca/triggers/` — one resolver per trigger type
4. `src/telcoscope/rca/engine.py` — rule evaluation + ranking
5. `src/telcoscope/rca/persistence.py` — upsert into
   `analytics.rca_hypotheses` (same shape as
   `incidents/persistence.py`, idempotent on
   `(incident_id, hypothesis_rank)`)
6. Seed rule library: 3–5 rules in `rca/rules/transport.yml` as the
   first bundle, enough to validate end-to-end
7. `tests/rca/` — one test file per module, one fixture-driven test
   per seeded rule
8. `make rca` target wiring, HLD + Cheatsheet updates
