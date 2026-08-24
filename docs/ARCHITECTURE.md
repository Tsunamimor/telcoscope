# Architecture

This document describes the current architecture of `telcoscope`. For the
*reasoning* behind the design choices — and the trade-offs against earlier
industry patterns — see [`ARCHITECTURE_EVOLUTION.md`](ARCHITECTURE_EVOLUTION.md).

## Component overview

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Synthetic data  │    │  PM / FM / CM    │    │  External CSV /  │
│  generator       │    │  feeds (future)  │    │  Parquet sources │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │   Ingest layer     │
                       │   (Python +        │
                       │   Pydantic         │
                       │   validation)      │
                       └─────────┬──────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │   PostgreSQL + TimescaleDB          │
              │                                     │
              │   - pm_measurements  (hypertable)   │
              │   - fm_alarms        (hypertable)   │
              │   - cm_changes       (SCD2)         │
              │   - dim_counter, dim_cell, ...      │
              │   - mart_kpi_cell_hourly  (dbt)     │
              │   - mart_kpi_enb_hourly   (dbt)     │
              │   - anomalies                       │
              │   - incidents                       │
              └──────────────────┬──────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
┌───────▼────────┐      ┌────────▼────────┐      ┌────────▼────────┐
│   Detection    │      │   RCA engine    │      │   Grafana       │
│   (statistical │─────▶│   (YAML rules + │      │   dashboards    │
│   + ML)        │      │   correlation)  │      │                 │
└────────────────┘      └────────┬────────┘      └─────────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │  LLM narrator      │
                       │  (Anthropic API,   │
                       │   mockable)        │
                       └─────────┬──────────┘
                                 │
                       ┌─────────▼──────────┐
                       │  Alerts + Streamlit│
                       │  incident inspector│
                       └────────────────────┘
```

## Layers

### 1. Raw / landing layer (long format)

Single fact table for all PM counters:

```
pm_measurements (
  ts          timestamptz,         -- measurement interval start
  enb_id      bigint,
  cell_id     bigint,
  counter_id  int,                 -- FK to dim_counter
  value       double precision,
  PRIMARY KEY (ts, cell_id, counter_id)
)
```

This is a TimescaleDB hypertable partitioned by `ts`. New vendors or new
counters require only inserts into `dim_counter` — no schema changes.

`fm_alarms` and `cm_changes` follow the same long-format pattern.

### 2. Dimension layer

- `dim_counter` — counter catalogue with `name`, `description`, `kpi_group`,
  `vendor`, `technology`, `numerator_of`, `denominator_of`
- `dim_cell` — cell identity, sector, archetype (urban / suburban / rural)
- `dim_enb` — eNB identity, site, region
- `dim_vendor` — vendor identifier
- `dim_technology` — LTE / 5G NR (placeholder for future)

### 3. Transformation layer (dbt)

- **staging models** — light type casts and filtering off raw long-format tables
- **intermediate models** — joins with dimensions, KPI-component aggregations
- **marts** — vendor-agnostic KPI marts, wide format, one row per cell-hour
  or eNB-hour, per 3GPP TS 32.450 / TS 32.425 definitions

### 4. Detection layer

Two implementations of the same interface:

- **Statistical** — rolling robust z-score with hour-of-week seasonality
  adjustment. Cheap, transparent, defensible.
- **ML** — Isolation Forest over a per-cell-per-hour multivariate KPI vector.
  Catches multivariate anomalies the univariate baseline misses.

Both write detections into the `anomalies` table with method, score, severity.

### 5. RCA engine

When an anomaly is persisted, the engine evaluates a YAML-defined rule library
against context:
- Concurrent FM alarms on the same cell / eNB / region (configurable window)
- Recent CM changes on the same cell / eNB
- Anomalies on neighbour cells in the same time window

Output: a ranked list of RCA hypotheses, each with confidence score and
suggested actions, persisted into the `incidents` table.

### 6. LLM narrator

Stateless service that takes an incident record (anomaly + ranked hypotheses +
relevant alarms + cell context) and returns a human-readable incident summary
via the Anthropic API. Has a `mock` mode for CI and offline development that
returns a deterministic template summary, so the rest of the pipeline can be
tested without API access.

### 7. Alerting and presentation

- Grafana dashboards (provisioned as code in `infra/grafana/`)
- Grafana alerts → webhook → notifier service (email / Slack)
- Streamlit "Incident Inspector" app for drill-down

## Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| Database | PostgreSQL 16 + TimescaleDB | Open source, time-series-aware, runs anywhere, SQL-native, simple operational model |
| Transformations | dbt-core | Version-controlled, testable, documented, lineage graph "for free" |
| Detection | scikit-learn + statsforecast | Mature, well-documented, recruiter-recognised |
| Orchestration | Make + cron (v1) | Smallest moving parts; can upgrade to Prefect/Dagster later |
| Alerting | Grafana → webhook | Grafana already deployed; native UI for alert configuration |
| Dashboards | Grafana (ops) + Streamlit (analyst) | Different audiences need different surfaces |
| LLM | Anthropic API (Claude Haiku) | Cheap, fast, switchable; easy to mock for CI |
| Cloud (optional) | AWS Free Tier + Terraform | Familiar to most operators; cheap demo path |
