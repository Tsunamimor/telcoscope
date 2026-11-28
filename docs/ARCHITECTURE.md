# telcoscope — High-Level Design

> A reference document describing the architecture of the telcoscope
> project — the design intent, the layered structure, the data flows,
> the technology choices, and where the boundaries live between
> components.
>
> This is a "conceptual" document, distinct from the week-by-week
> implementation guides. Read this to understand *what* the system
> is and *why* it's shaped the way it is. Read the weekly guides
> to build it.

---

## 1. What telcoscope is

**One-sentence definition.** A vendor-agnostic 3GPP KPI observability
and root-cause analysis platform for mobile networks, small enough
to run entirely on a laptop, production-shaped enough to demonstrate
current best practice in telecoms analytics.

**Who it's for.**

- **Portfolio audience** — hiring managers at telecoms vendors
  (Ericsson, Nokia, Samsung, Mavenir) and operators (BT, Vodafone,
  Deutsche Telekom) looking for candidates who bridge deep RAN
  domain expertise with modern data engineering practice.
- **Reference audience** — network operations teams wanting a
  worked example of how to bring modern data-stack tooling (dbt,
  TimescaleDB, GenAI) to a domain that historically ran on
  vendor-locked reporting suites.

**What it isn't.** Not a production replacement for Tier 1
operator RAN analytics. Real operator PM data is 3–4 orders of
magnitude larger; real OSS integrations we don't model; real SLAs
we don't claim. This is a reference implementation of the
*patterns* at a scale that fits on a laptop.

---

## 2. Design goals

The design is optimised for these outcomes, in order:

1. **Vendor-agnostic KPI definitions.** The same KPI formula works
   whether the underlying counters came from Vendor A or Vendor B.
   Achieved by a counter dictionary (`dim_counter`) that maps
   vendor-specific names onto logical counter names, plus KPI
   formulas that reference logical names only.

2. **One-command local deploy.** `git clone && make up && make seed
   && make dbt` in under 5 minutes on a fresh machine. This is the
   quickstart promise — everything else in the design supports it.

3. **Honest anomaly detection performance.** Every detector claim
   (precision, recall) must be verifiable. Achieved by
   synthetic-first data generation with ground-truth-labelled
   anomalies persisted to a `synth_truth` table.

4. **Portable, not scale-focused.** Postgres+TimescaleDB fits on
   a laptop and scales to Tier 3 operator size without changes.
   Beyond that, the same design patterns apply on Snowflake,
   BigQuery, Databricks — the tools change, the layered
   architecture doesn't.

5. **Extensible along one axis at a time.** Adding a new vendor is
   a config change (`dim_counter`). Adding a new KPI is a new dbt
   model. Adding a new RCA pattern is a YAML entry. Adding a new
   detector is a new class implementing the detection interface.
   Each axis of extension is deliberately kept independent of the
   others.

---

## 3. Layered architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Data sources                                                  │
│   (v1: synthetic generator; v2: real vendor CSV/Parquet feeds)  │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Ingestion layer                                               │
│   Python + Pydantic validation, psycopg COPY bulk load          │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Storage layer — PostgreSQL 16 + TimescaleDB                   │
│                                                                 │
│    raw (long format)     dims                analytics          │
│    ──────────────────    ─────────────────   ──────────────     │
│    pm_measurements       dim_counter         anomalies          │
│    fm_alarms             dim_cell            incidents          │
│    cm_changes            dim_enb             synth_truth        │
│                          dim_vendor          rca_hypotheses     │
│                          dim_technology                         │
│                                                                 │
│    Hypertables: pm_measurements, fm_alarms                      │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Transformation layer — dbt                                    │
│                                                                 │
│    staging          intermediate                marts           │
│    ────────         ────────────────────        ─────────       │
│    stg_pm_meas...   int_kpi_components_cell...  mart_kpi_cell_hly│
│                                                 mart_kpi_enb_hly│
│                                                 mart_incidents_ │
│                                                   timeline      │
│                                                 mart_detector_  │
│                                                   evaluation    │
│                                                                 │
└──────────┬──────────────────────────────────────────────────────┘
           │                                             │
           ▼                                             ▼
┌───────────────────────────┐              ┌───────────────────────┐
│                           │              │   Presentation layer  │
│   Detection layer         │              │                       │
│                           │              │   - Grafana (ops):    │
│   - Statistical baseline  │              │     KPI overview,     │
│     (modified z-score,    │              │     incidents ops     │
│     seasonal baseline)    │              │     dashboard         │
│   - Isolation Forest      │              │   - Streamlit         │
│     (multivariate ML)     │              │     (analyst /        │
│                           │              │     incident inspector│
│   Outputs: analytics.     │              │     — Wk 5)           │
│   anomalies table, with   │              │   - FastAPI (Wk 5)    │
│   per-method precision/   │              │                       │
│   recall vs synth_truth   │              └───────────────────────┘
│                           │
└──────────┬────────────────┘              ┌───────────────────────┐
           │                               │   Alerting            │
           ▼                               │                       │
┌───────────────────────────┐              │   notifier.py → HTTPS │
│   Grouper                 │              │   webhook (self-      │
│                           │              │   hosted webhook-     │
│   (2h gap threshold,      │              │   tester on Synology  │
│   max-severity rollup,    │              │   NAS or any JSON     │
│   per cell_id)            │─────────────▶│   endpoint)           │
│                           │              │                       │
│   Outputs: analytics.     │              │   Idempotent: tracks  │
│   incidents (one row per  │              │   notified_at per     │
│   contiguous event)       │              │   incident            │
└──────────┬────────────────┘              └───────────────────────┘
           │
           ▼
┌───────────────────────────────────────────────────────────────┐
│   RCA layer (DEC-006 — rules-first, YAML-driven, per-incident)│
│                                                                │
│   - Rule library (rca/rules.yaml)                              │
│   - Trigger resolvers (rca/triggers/):                         │
│       concurrent_fm_alarm, recent_cm_change,                   │
│       neighbour_cell_anomaly, kpi_pattern                      │
│   - Engine (rca/engine.py) — pure retriever, AND semantics,    │
│     weakest-link confidence (rule.confidence × min strength)   │
│   - Persistence (rca/persistence.py) — DELETE+INSERT per       │
│     incident; set of hypotheses always reflects latest run     │
│   - LLM narrator (Wk 5 Day 4) — renders hypotheses as prose    │
│                                                                │
│   Outputs: analytics.rca_hypotheses (one row per (incident_id, │
│   hypothesis_rank), top N=5 by confidence, evidence as JSONB   │
│   with self-contained rule snapshot)                           │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. Data flow — from source to pixel

Section 3 shows *what components exist*. This section describes what
happens to data *as it moves between them* — the transformation chain
from vendor-native CSVs at the source end to a rendered chart pixel
at the display end. Each hop is a translation: it has a specific
input contract, a specific output contract, and a specific
responsibility. When something looks wrong in the final chart, the
question "at which translation stage did it go wrong?" localises the
debugging.

### 4.1 The pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  ①  Source feeds (external to telcoscope)                            │
│     PM CSV / FM CSV / CM CSV — vendor-native format                  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Python ingester
                               │  (Pydantic validation, type casting,
                               │   vendor-name → logical-name mapping
                               │   via dim_counter)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ②  Raw layer — Postgres schema: raw                                 │
│     Long-format tables, TimescaleDB hypertables                      │
│     One row per (ts, cell, counter) — append-only                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  dbt staging model
                               │  (light casts, filters, drops nulls,
                               │   materialised as a view)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ③  Staging layer — schema: dbt_dev_staging                          │
│     stg_pm_measurements (view)                                       │
│     One row per raw measurement — still long format                  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  dbt intermediate model
                               │  (join to dim_counter for logical
                               │   names, pivot counters into columns,
                               │   group to hourly grain)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ④  Intermediate layer — schema: dbt_dev_intermediate                │
│     int_kpi_components_cell_hourly (table)                           │
│     One row per (cell, hour) — 14 counter columns, pre-pivoted       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  dbt mart model
                               │  (apply 3GPP KPI formulas,
                               │   handle NULL / divide-by-zero,
                               │   materialised as a table)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ⑤  Marts layer — schema: dbt_dev_marts                              │
│     mart_kpi_cell_hourly (table)                                     │
│     One row per (cell, hour) — 6 vendor-agnostic KPIs                │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Grafana panel query (per-panel SQL)
                               │  time_bucket() for chart grain
                               │  cell_id::text AS metric
                               │  avg(kpi_column) AS value
                               │  $__timeFilter(ts) for range
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ⑥  Panel query result set — in-flight rows                          │
│     (time, metric, value) tuples, one per (bucket, cell)             │
│     Ephemeral — exists only while the query runs                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Grafana Postgres plugin
                               │  (recognises time/metric/value contract,
                               │   builds Grafana's internal "frame")
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ⑦  Grafana time-series frame (in-memory)                            │
│     Apache Arrow columnar buffer                                     │
│     One "field" per unique metric value → one line on the chart      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Grafana visualisation engine
                               │  (unit conversion, colour assignment,
                               │   axis scaling, legend generation,
                               │   thresholds, display-name templates)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ⑧  Rendered chart in the browser                                    │
│     SVG / Canvas — lines, axes, legend, tooltips                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Stage detail

Each stage below lists what it is, the shape data takes at that
stage, and what changed compared to the previous stage.

#### ① Source feeds *(external to telcoscope)*

- **What.** Vendor-native CSV or Parquet files from an operator's OSS
  (Operations Support System) or EMS (Element Management System). One
  file per network element per reporting interval — typically
  15-minute or hourly aggregations.
- **Shape.** Wide, sparse, vendor-proprietary. Column names like
  `0x0342_RRC_Setup_Att` or `M8005C0`. Timestamps often in mixed time
  zones. Format varies by vendor and product generation.
- **Change vs previous.** N/A — this is the entry point. In v1
  `telcoscope`, the synthetic generator produces data in this same
  shape internally rather than reading real feeds.

#### ② Raw layer *(Postgres `raw` schema)*

- **What.** Long-format hypertables: `pm_measurements`, `fm_alarms`,
  `cm_changes`. Append-only, partitioned by time via TimescaleDB.
- **Shape.** Regular. One row = one atomic observation:
  `(ts, cell_id, counter_id, value)`. Approximately 1 million rows per
  100 cells per month at hourly grain.
- **Change vs previous.** Vendor-specific counter names replaced by
  `counter_id` foreign keys to `dim_counter`. Timestamps normalised to
  UTC. Wide-and-messy became long-and-regular. This is where the
  vendor-agnostic transformation *begins* — but the counters are
  still just numeric IDs; their *meaning* lives in `dim_counter`.

#### ③ Staging layer *(dbt schema `dbt_dev_staging`)*

- **What.** Thin dbt views over raw tables. Zero storage cost — a view
  is just a named query.
- **Shape.** Identical grain to raw. Same row count.
- **Change vs previous.** Explicit type casts, filtered-out-nulls in
  composite-key columns. Structurally almost no change. The purpose
  is not to transform but to *isolate downstream models from raw
  schema evolution* — if a raw column is added or renamed, only this
  layer needs updating.

#### ④ Intermediate layer *(schema `dbt_dev_intermediate`)*

- **What.** A materialised table with counters pivoted into columns:
  `int_kpi_components_cell_hourly`.
- **Shape.** One row per (cell, hour). 14 counters become 14 columns.
  Row count drops roughly 14× vs staging.
- **Change vs previous.** Three transformations at once: joined to
  `dim_counter` to resolve logical counter *names*
  (`RRC_CONN_SETUP_ATT` etc.), aggregated to hourly grain via `SUM`,
  and pivoted using `MAX(CASE WHEN counter_name = 'X' THEN value END)`.
  Format shifted from long-and-narrow to wide-and-analytical.
  Materialised (persistent, indexed) rather than a view because two
  marts read from it — cheaper to build once than compile inline
  twice.

#### ⑤ Marts layer *(schema `dbt_dev_marts`)*

- **What.** The user-facing analytical tables: `mart_kpi_cell_hourly`,
  `mart_kpi_enb_hourly`, plus two Week 4 marts —
  `mart_incidents_timeline` (view joining incidents to KPI values at
  ts_start and a 24h-baseline) and `mart_detector_evaluation`
  (precision/recall per detector method vs `synth_truth`).
- **Shape.** Same grain as intermediate (one row per cell-hour) but
  columns are *KPIs*, not raw counters. 14 counter columns become 6
  KPI columns.
- **Change vs previous.** The 3GPP KPI formulas applied
  (`succ::numeric / att * 100`, drop-rate ratios, etc.). NULL and
  divide-by-zero cases handled explicitly. Downstream consumers now
  see rates and percentages, not raw counter counts. This is the
  layer that a network engineer, BI tool, or hiring manager actually
  looks at.

#### ⑥ Panel query result set *(ephemeral)*

- **What.** The rows Postgres returns when Grafana runs a panel's SQL.
  Not stored anywhere — created, transmitted, discarded within a
  fraction of a second.
- **Shape.** Three columns: `time`, `metric`, `value`. Several
  thousand rows per panel refresh — one per (time-bucket, series)
  combination.
- **Change vs previous.** Time re-bucketed to the chart's display
  grain via `time_bucket()`. Only *one* KPI column selected from the
  mart (becomes `value`). `cell_id` cast to text and renamed
  `metric` so Grafana knows to split series by it. Filtered to the
  dashboard's time range via `$__timeFilter(ts)`.

#### ⑦ Grafana time-series frame *(in-memory)*

- **What.** Grafana's internal representation of the data — a columnar
  Apache Arrow buffer held in the Grafana server's RAM.
- **Shape.** One "field" per unique `metric` value. 10 cells → 10
  fields, each holding an array of Y-values indexed by the shared
  time array.
- **Change vs previous.** Query rows pivoted long-to-wide-in-memory.
  Each series became an independent numeric field ready for the
  renderer. This is what makes drawing one line per cell efficient.

#### ⑧ Rendered chart *(browser SVG/Canvas)*

- **What.** The visual output the user actually sees.
- **Shape.** No longer data — pixels. Lines, axis labels, tick
  marks, tooltips, legend entries.
- **Change vs previous.** Everything the visualisation options
  control: unit conversion (bare numbers → "27.5 Mbps"), colour
  assignment, axis scaling, legend labelling via display-name
  templates, threshold bands.

### 4.3 Two observations worth internalising

**Row count contracts.** Each stage has a different grain. The two
big pivots — raw → intermediate (long-to-wide, collapses ~14×) and
mart → panel query (wide-to-long-again for chart series) — are
where the interesting transformations happen. When performance
becomes an issue, these are the first places to look.

**Semantic level rises through the chain.** Raw counters mean
nothing without deep telecoms domain knowledge. Marts speak in 3GPP
KPIs — a network engineer understands them immediately. Panel
visualisations speak in *pictures* — anyone can see "something
dropped last Tuesday". Each layer's audience broadens. This is the
whole point of an analytics engineering pipeline: turn technical
data into business-legible insight, one deliberate step at a time.

### 4.4 Why the translation framing matters for debugging

When a chart looks wrong, the fastest way to isolate the cause is to
ask *which translation layer* misbehaved:

| Symptom | Likely layer | Where to look |
|---|---|---|
| Bad numbers on chart | Mart (⑤) | Query the mart directly in Adminer — is the data itself wrong? |
| Right numbers, no chart drawn | Panel query → Frame (⑥→⑦) | Check `time` / `metric` / `value` column aliases; check Format is "Time series" |
| Chart drawn but ugly | Visualisation engine (⑧) | Panel display options: unit, axis, colour, legend |
| Chart looks fine but misleads | SQL query (⑥) | Check aggregation, WHERE clause, GROUP BY |
| Missing counters entirely | Ingestion (①→②) | Check the counter dictionary — was the vendor mapping ever added? |

The systematic answer to "why doesn't this chart look right?" is
never "look at everything". It's "at which translation stage did the
data lose its way?" — then check that one stage in isolation.

---

## 5. The four architectural pillars

Four design decisions do most of the work. Each has an alternative
that could have been chosen; each is defensible under scrutiny.

### 5.1 Long-format raw layer, wide marts

**The choice.** Store raw counter data in a long/narrow format —
one row per `(timestamp, cell, counter)` — rather than one column
per counter. Wide is built downstream by dbt via pivot.

**The alternative.** Wide tables per measurement domain (one column
per counter), the mid-2010s convention documented in
`ARCHITECTURE_EVOLUTION.md`.

**Why long won.** Adding a new counter or a new vendor becomes an
`INSERT` into `dim_counter`, not a DDL change. The staging model
handles the pivot generically. Vendor introduction, which is a
critical-path event in operator lifecycles, becomes a config change
rather than an engineering project.

**Cost of the choice.** The pivot in the intermediate layer is a
bit of ceremony. On the scale we handle (~1M rows / month / 100
cells), it's fast. On Tier 1 operator scale it would need
materialisation optimisations.

### 5.2 Vendor-agnostic counter dictionary

**The choice.** `dim_counter` maps every vendor's proprietary
counter name onto a *logical* counter name (like
`RRC_CONN_SETUP_ATT`). KPI formulas reference logical names only.

**The alternative.** Encode vendor differences into separate KPI
models — one `mart_kpi_cell_hourly_vendor_a`, another
`_vendor_b`.

**Why the dictionary won.** Two operators running multi-vendor
RAN portfolios can compute the same 3GPP KPI across their entire
network with one formula. The dictionary absorbs vendor difference;
downstream never sees it.

**Cost.** Setting up the dictionary correctly requires domain
knowledge — you have to know that vendor A's `0x0342_RRC_Setup_Att`
is the same underlying 3GPP quantity as vendor B's
`RRC.ConnEstabAtt.Sum`. This is where your 25 years of RAN
experience becomes uncopyable IP.

### 5.3 Ground-truth-labelled synthetic data

**The choice.** Generate synthetic data with realistic seasonality
plus explicitly injected anomalies, persist the injection plan as
ground truth.

**The alternative.** Real public anonymised PM data from Kaggle
etc.

**Why synthetic won.** Real public datasets don't come with
labelled anomalies, so any detector claim is unverifiable ("I
built an anomaly detector" — "OK, how well does it work?" —
"…um"). Synthetic gives honest precision/recall numbers.

**Cost.** The synthetic data has to be realistic enough to be
credible. Getting the seasonality, archetype variation, and
anomaly patterns right takes real thought — it's the four-hour
Day 4 in Week 1.

### 5.4 YAML-driven RCA rule library

**The choice.** Encode RCA patterns ("if accessibility drops and
an S1 transport alarm is present within 15 minutes, likely cause
is transport failure") as YAML entries in `rca/rules.yaml`. A
generic engine evaluates all rules against every incident and
produces ranked hypotheses in `analytics.rca_hypotheses`.

**The alternative.** Hard-code RCA logic in Python; or, further,
replace rules with a learned classifier or an LLM-based RCA.

**Why YAML won.** RCA patterns are domain knowledge that changes
frequently and doesn't need to change with code releases. A
network engineer with no Python skills can propose a new rule.
The rule library becomes a *product* — the tangible
representation of a team's operational knowledge. See **DEC-006
§4** for why rule-learning and LLM-based RCA are deferred (no
labelled training data for rule learning today; LLM hides the
telecom-specific knowledge that makes this project credible).

**Cost.** The engine is more code than the hard-coded version —
pydantic schema (`rca/schema.py`), four trigger resolvers
(`rca/triggers/`), a pure evaluator (`rca/engine.py`), and a
DELETE+INSERT persistence layer (`rca/persistence.py`) — but the
payoff scales with rule count. Shipped end-to-end in Week 5 Day 2.

---

## 6. Component boundaries and responsibilities

Each component owns exactly one thing. This is what makes the
system extensible along independent axes.

### Ingestion (`src/telcoscope/ingest/`, `src/telcoscope/synth/`)

**Owns.** Getting external data into `raw.*` tables.

**Doesn't own.** Interpreting the data, computing KPIs, deciding
what's normal.

**Extension shape.** Adding a new source (e.g. a real vendor CSV
feed) means writing a new ingester module that lands rows in
`raw.pm_measurements`. Nothing downstream changes.

### Storage (`db/migrations/`, `src/telcoscope/db/`)

**Owns.** The schema — table shapes, primary keys, indexes,
hypertable configuration, foreign-key integrity.

**Doesn't own.** What the data means, how it's transformed.

**Extension shape.** Adding a new table is a new Alembic
migration + new SQLAlchemy model class. Adding TimescaleDB-
specific features (continuous aggregates, compression) is a
manual migration.

### Transformation (`dbt/`)

**Owns.** Turning raw data into KPI marts. Sources, tests,
documentation, lineage.

**Doesn't own.** How raw data arrived. How marts are consumed.
Business intelligence dashboarding.

**Extension shape.** Adding a new KPI is a new expression in
`mart_kpi_cell_hourly.sql` plus a docs entry. Adding a new mart
grain (e.g. per-region hourly, per-vendor daily) is a new mart
file. Adding a new source is an entry in `_sources.yml`.

### Detection (`src/telcoscope/detect/`)

**Owns.** Reading from the marts, producing anomaly rows in
`analytics.anomalies` with method, severity, score. Two detectors
share a common interface (DEC-003): a statistical modified z-score
detector (per-KPI seasonal baseline) and an Isolation Forest
multivariate ML detector. Severity thresholds are calibrated per
detector from `abs(score)` percentiles (DEC-005) — IF uses tighter
minor thresholds to preserve precision.

**Doesn't own.** Explaining anomalies. Alerting. Displaying
anomalies.

**Extension shape.** A new detector implements the `Detector` ABC
and gets registered by name. Comparison between methods happens
by joining against `synth_truth` and computing precision/recall per
method (`mart_detector_evaluation`).

### Incident grouping (`src/telcoscope/incidents/`)

**Owns.** Collapsing per-anomaly rows into contiguous incident
records in `analytics.incidents`, keyed on
`(cell_id, ts_start)`. The grouper uses a 2h-silence threshold
(DEC-004) and a max-severity roll-up; UPSERT on the unique index
makes the whole pipeline idempotent — `make incidents` is safe to
re-run with no duplication.

**Doesn't own.** Detection. RCA. Alerting via the webhook pass
lives in `incidents/notifier.py` and is called at the tail of
`incidents/run.py`.

**Extension shape.** New fields on the incident (e.g. a
cluster_id for multi-cell events) are migrations plus grouper
output changes. New grouping policies (e.g. 1h gap instead of 2h)
are configuration, not code.

### RCA (`src/telcoscope/rca/`)

**Owns.** Correlating each incident with concurrent FM alarms,
recent CM changes, neighbour-cell anomalies, and KPI drop/spike
signatures, producing ranked hypotheses in
`analytics.rca_hypotheses` keyed on
`(incident_id, hypothesis_rank)`. The module ships five pieces
(DEC-006 §6):

- **Rule library** (`rca/rules.yaml`) — 5 seed rules covering
  transport, hardware, CM, cluster-wide and handover patterns.
- **Schema** (`rca/schema.py`) — pydantic-validated `Rule`,
  `RuleLibrary`, and a discriminated `Trigger` union over four
  trigger types (`concurrent_fm_alarm`, `recent_cm_change`,
  `neighbour_cell_anomaly`, `kpi_pattern`).
- **Trigger resolvers** (`rca/triggers/`) — one SQL-executing
  resolver per trigger type, each returning
  `MatchResult(evidence, strength)` or `None`.
- **Engine** (`rca/engine.py`) — AND-semantic evaluator with
  weakest-link confidence (`rule.confidence × min strength`),
  top-N ranking, rule-snapshot capture so stored hypotheses stay
  interpretable after rule-library changes.
- **Persistence** (`rca/persistence.py`) — DELETE + INSERT in one
  transaction per incident; a re-run with fewer matches leaves no
  stale high-rank rows behind.

Orchestration runs through `python -m telcoscope.rca.run`
(aliased as `make rca`), env-var configurable
(`RCA_TOP_N`, `RCA_INCIDENT_SEVERITY_FILTER`,
`RCA_MAX_INCIDENTS`, `RCA_RULES_PATH`).

**Doesn't own.** Detecting anomalies. Grouping anomalies into
incidents. Narrating hypotheses to a human (that's the Week 5
Day 4 LLM narrator).

**Extension shape.** New RCA patterns are YAML entries in
`rca/rules.yaml` — reviewable in git by anyone, including a
network engineer with no Python. New correlation contexts are new
`Trigger` subclasses in `rca/schema.py` plus a resolver function
in `rca/triggers/`.

### Narration (`src/telcoscope/narrate/`)

**Owns.** Turning structured incident records and their ranked
hypotheses into human-readable prose via an LLM. Cost management,
mock mode for CI, prompt templates.

**Doesn't own.** Determining what's an incident. Deciding when
to fire an alert. Generating the hypotheses themselves — that's
RCA's job.

**Extension shape.** New prompt templates for different audiences
(NOC vs field engineer vs C-suite summary). Swap the LLM provider
by changing one config entry.

### Alerting (`src/telcoscope/incidents/notifier.py`)

**Owns.** Getting incidents from `analytics.incidents` to a human
via an HTTPS JSON webhook. Env-var configurable rate-limit
(`INCIDENT_NOTIFY_SLEEP_SECONDS`) and per-run cap
(`INCIDENT_NOTIFY_MAX_PER_RUN`), idempotent on `notified_at` so
only unseen incidents are posted. Validated end-to-end in Week 4
against a self-hosted `tarampampam/webhook-tester` on a Synology
NAS — any JSON-accepting endpoint works (Slack incoming webhooks,
PagerDuty events API, ServiceNow, etc.).

**Doesn't own.** Deciding what's incident-worthy. Routing
(severity-based routing is on the backlog).

**Extension shape.** New notifiers implement the same simple
contract (`notify(payload) -> bool`). BKL-006 is open on
verifying the webhook endpoint identity — today a 2xx is trusted
even if the endpoint is a catch-all.

### Presentation (`apps/streamlit/`, `apps/api/`, `infra/grafana/`)

**Owns.** Displaying data to humans. Three audiences:

- **Grafana** — ops-shaped time-series dashboards. NOC-facing.
  Two shipped dashboards: a KPI overview (Weeks 1–2) and the
  Week 4 incidents-ops dashboard with severity filter, Top N
  bar chart, incident timeline, and incident table with a
  repeat-offender heat column.
- **Streamlit incident inspector** — analyst-shaped drill-down.
  Data-team-facing. Wk 5.
- **FastAPI service** — programmatic access. Automation-facing.
  Wk 5.

**Doesn't own.** Producing the data being displayed.

**Extension shape.** New Grafana dashboards are JSON files.
New Streamlit views are new Python files. New API endpoints
extend the FastAPI app.

---

## 7. Data model overview

Full details are in `docs/DATA_MODEL.md`. High-level summary:

### Raw layer (schema: `raw`)

Long-format tables. Every row represents one atomic event or
measurement. Optimised for append-only insertion.

| Table | Grain | Volume | Time-partitioned |
|---|---|---|---|
| `pm_measurements` | (ts, cell, counter) | ~1M rows / 100 cells / 30 days | Yes (7-day chunks) |
| `fm_alarms` | (uid, raised_at) | ~100/day for 100 cells | Yes (30-day chunks) |
| `cm_changes` | (uid) | ~10/day for 100 cells | No (SCD2) |

### Dimension layer (schema: `dims`)

Reference tables joined by facts. Low-volume, high-integrity.

- `dim_vendor` — vendor identifiers
- `dim_technology` — LTE, 5G_NSA, 5G_SA
- `dim_counter` — the abstraction that makes the system
  vendor-agnostic
- `dim_enb` — eNB identity and vendor
- `dim_cell` — cell identity, sector, archetype, coordinates

### Analytics layer (schema: `analytics`)

Derived tables produced by detection, grouping, and RCA.

- `anomalies` — one row per detection (method, severity, score,
  `anomaly_uid`). Populated by `detect/run.py`.
- `incidents` — one row per contiguous detection event per cell,
  keyed on `(cell_id, ts_start)` with a UUID `incident_id` PK and
  a UNIQUE index on the composite key. Populated by
  `incidents/run.py`. Tracks `notified_at` for the webhook pass.
- `synth_truth` — ground-truth labels for injected anomalies.
  Populated by the synthetic generator at seed time.
- `rca_hypotheses` — ranked RCA hypotheses per incident, one row
  per `(incident_id, hypothesis_rank)`. FK-cascading from
  `incidents(incident_id)`. Evidence stored as JSONB with a
  self-contained `rule_snapshot` so stored rows stay
  interpretable after rule-library changes. Populated by
  `rca/run.py`. See DEC-006.

`cell_id` is `BIGINT` across all four analytics tables (harmonised
in Week 5 Day 1 under BKL-004 / CLS-005), matching
`dims.dim_cell.cell_id` and `raw.pm_measurements.cell_id`. dbt
relationships tests in `_sources.yml` guard both
`anomalies.cell_id` and `incidents.cell_id` against
`dim_cell.cell_id` so the type can't silently drift again.

### Marts (schema: `dbt_dev_marts`)

Wide, vendor-agnostic KPI tables plus analytics-side marts
produced by dbt.

- `mart_kpi_cell_hourly` (table) — one row per (cell, hour)
- `mart_kpi_enb_hourly` (table) — one row per (eNB, hour)
- `mart_incidents_timeline` (view) — enriches
  `analytics.incidents` with KPI values at `ts_start` and the
  24h-baseline, plus per-KPI deltas. Drives the Grafana
  incidents-ops dashboard.
- `mart_detector_evaluation` (table) — precision / recall /
  attempts per detector method vs `synth_truth`. Honest numbers,
  no hand-waving.

---

## 8. Technology choices — a summary table

| Concern | Choice | Rejected | Reason |
|---|---|---|---|
| Container runtime | Docker Compose | Kubernetes | Compose fits in one file; K8s is overkill for a laptop-scale project |
| Database | PostgreSQL 16 + TimescaleDB | ClickHouse, Snowflake | Runs anywhere, mature, time-series-aware, has PostGIS if we need it later |
| Migrations | Alembic | Flyway, plain SQL scripts | Alembic pairs with SQLAlchemy for autogenerate; standard in Python data stacks |
| ORM | SQLAlchemy 2.0 | Django ORM, raw psycopg | 2.0 has proper Python-3 type hinting; the industry default outside Django |
| DB driver | psycopg3 | psycopg2 | Async-capable, better type handling, JSONB via `psycopg.types.json.Jsonb` |
| Transformations | dbt-core | Airflow SQL, custom Python | Version-controlled, tested, documented, lineage — this is the industry standard |
| Python data | Polars + Pandas | Pandas only, DuckDB | Polars is 10-100× faster for typed columnar work; Pandas kept for interop |
| Bulk load | psycopg `COPY` | SQLAlchemy `bulk_insert_mappings` | `COPY` is ~100× faster for the fact load |
| Detection ML | scikit-learn IsolationForest + statistical modified z-score | Prophet, deep learning | Mature, fast, explainable — the right level for portfolio scale |
| Rule engine | YAML + pydantic (discriminated union) | Drools, custom DSL, rule learning, LLM-based RCA | YAML is readable by non-devs; pydantic gives validation for free; rule-learning / LLM paths parked per DEC-006 exit criteria |
| LLM | Anthropic (Claude Haiku) | OpenAI, local Ollama | Cheap enough that mock mode is optional; API-swappable |
| Dashboards | Grafana | Superset, Metabase | Grafana handles time-series natively; has provisioning-as-code |
| Analyst UI | Streamlit | Dash, Panel | Streamlit is fastest to iterate on for a small team |
| API | FastAPI | Flask | FastAPI has async, OpenAPI docs, and pydantic integration by default |
| Alerting | HTTPS JSON webhook + self-hosted webhook-tester | Slack SDK, PagerDuty library | Wire-level neutral; any endpoint works; self-hosted tester on Synology NAS avoids public-service rate limits |
| Logging | Loguru | structlog, stdlib logging | Loguru's `logger.info("…{}", arg)` is concise and the project convention |
| CI | GitHub Actions | GitLab CI, CircleCI | Free for public repos; universally recognised |
| Environment | conda-then-pip | pip-only, uv-only | conda gives Python + the tricky binaries; pip handles the rest |

---

## 9. Deployment model

Three deployment shapes, in increasing complexity:

### 9.1 Local (v1 — the default)

```
Laptop
├── Docker Desktop (WSL2 backend on Windows)
│   ├── telcoscope-postgres (Postgres + TimescaleDB)
│   ├── telcoscope-grafana
│   └── telcoscope-adminer
├── Python venv / conda environment
│   ├── telcoscope package (editable install)
│   ├── dbt-core + dbt-postgres
│   └── Alembic
├── (Optional) Synology NAS on same LAN
│   └── tarampampam/webhook-tester → catches incident notifications
└── User's browser
    ├── http://localhost:3000 → Grafana
    ├── http://localhost:8080 → Adminer
    └── http://localhost:8081 → dbt docs (when running)
```

Zero external dependencies. Runs offline. Data lives in a named
Docker volume. The optional NAS gives you a persistent,
unthrottled webhook sink for Week 4+ incident-notifier work.

### 9.2 AWS Free Tier (v1.1 — stretch goal)

Documented as Terraform in `infra/terraform/aws/`. Same
component boundaries; different runtime hosts:

- RDS `db.t3.micro` Postgres (Free Tier eligible for 12 months)
- S3 bucket for landing zone
- Lambda triggered on S3 put → runs the ingester
- EC2 `t3.micro` or App Runner for Grafana + Streamlit

Cost target: $0 for 12 months, ~$5/month thereafter if not
torn down. Adds ~4–8 hours of implementation.

### 9.3 Production (out of scope, referenced only)

For a real Tier 1 operator this would look nothing like the
above — likely Databricks or Snowflake for the warehouse,
Kafka for streaming ingestion, a proper alerting stack
(PagerDuty), K8s for compute, and OSS/BSS integration for
alarm feeds. The design *patterns* transfer (long raw / wide
marts, dbt for transformation, vendor-agnostic counter
dictionary, YAML rule library); the *tools* change.

---

## 10. Extension roadmap

Ordered by cost/value ratio, most attractive first.

### 10.1 Project week-by-week status

- **Week 1** ✓ — scaffold, synthetic generator, raw + dims schemas
- **Week 2** ✓ — counter dictionary, dbt sources / staging /
  intermediate / marts, KPI definitions
- **Week 3** ✓ — anomaly detection (statistical + IF), evaluated
  honestly against `synth_truth` (DEC-003, DEC-005)
- **Week 4** ✓ — incident grouping (DEC-004), timeline mart,
  Grafana ops dashboard, webhook notifier with Synology NAS
- **Week 5** — in progress
  - Day 1 ✓ — BKL-004 `cell_id` harmonisation to BIGINT
    (CLS-005), dbt relationships guards
  - Day 2 ✓ (in review) — DEC-006 RCA engine end-to-end
    (migration, schema, 4 trigger resolvers, engine, persistence,
    `make rca`)
  - Day 3 — LLM narrator against `rca_hypotheses`
  - Day 4 — Streamlit incident inspector
  - Day 5 — FastAPI service
- **Week 6** — pytest coverage, CI green, README case study
- **Week 7** — optional AWS deploy
- **Week 8** — LinkedIn essay and interview prep

### 10.2 v2 candidates (worth a paragraph in the README's roadmap)

- **5G NR counter set** — the dimension model was designed for
  this; adding it is `dim_technology` inserts + new counter
  entries in `dim_counter`
- **Streaming ingestion** — Kafka topic per measurement type,
  dbt incremental models to catch up in near-real-time
- **Lakehouse variant** — Iceberg + DuckDB, for analytical
  workloads that outgrow Postgres
- **Multi-tenant** — one telcoscope instance serving multiple
  networks (each becomes a `network_id` dimension)
- **Handover-graph enrichment** — using neighbour-cell metadata
  to enrich anomaly context beyond the current "cells on same
  eNB" heuristic
- **Rule learning / LLM-based RCA** — deferred per DEC-006 §5.3.
  Triggered when the rule library grows past ~40 entries with
  >20% unmatched incidents, or when the narrator consistently
  rediscovers patterns the library doesn't encode.
- **Predictive maintenance** — from anomaly *detection* to
  anomaly *forecasting* using survival analysis on the historical
  incident record

### 10.3 Explicit non-goals

Things worth naming as *deliberately not built*, because the
"what didn't you build" answer signals as much seniority as the
"what did you build" one:

- No custom UI framework — Grafana + Streamlit is enough
- No custom orchestrator — Make + cron is sufficient at this scale
- No streaming until the batch story is watertight
- No K8s until the Docker Compose story stops fitting
- No deep-learning models until statistical/tree-based ones can be
  shown to be inadequate
- No learned RCA until the rules library's limits are visible
  (DEC-006 exit criteria)

---

## 11. What this document isn't

To keep this focused:

- **Not a data dictionary** — see `docs/DATA_MODEL.md`
- **Not a KPI specification** — see `docs/KPI_DEFINITIONS.md`
- **Not an evolution rationale** — see `docs/ARCHITECTURE_EVOLUTION.md`
- **Not an implementation guide** — see the weekly guides
- **Not a design decision log** — see `docs/decisions/DEC-00*.md`
  (DEC-001 scaffold, DEC-002 KPI dictionary, DEC-003 detector
  interface, DEC-004 incidents grouping model, DEC-005 severity
  calibration, DEC-006 RCA engine)
- **Not an interview cheat sheet** — but reading it aloud once
  or twice gives you fluent vocabulary for the standard
  "walk me through this project" ask

---

## 12. One-paragraph elevator pitch

If someone asks you to describe the project in 30 seconds — say
this:

> telcoscope is a vendor-agnostic 3GPP KPI observability
> platform for mobile networks. It ingests performance, fault,
> and configuration data into a long-format raw layer in
> Postgres+TimescaleDB, transforms it via dbt into wide KPI
> marts covering the five 3GPP KPI families, detects anomalies
> with statistical baselines and Isolation Forest, groups
> anomalies into incidents, correlates each incident against a
> YAML rule library producing ranked RCA hypotheses, and
> notifies via webhook — all with honest precision/recall
> numbers from a synthetic-with-ground-truth data generator.
> An LLM narrator and Streamlit inspector follow in Week 5.
> It's small enough to run on a laptop with one command,
> production-shaped enough to demonstrate current best
> practice. I built it to bridge 25 years of RAN experience
> with modern data engineering.

That's the version to have memorised.
