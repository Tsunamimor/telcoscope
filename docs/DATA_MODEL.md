# Data Model

> Entity definitions, table schemas, and relationships for `telcoscope`.

## Conceptual model

```
                ┌──────────────┐
                │ dim_vendor   │
                └──────┬───────┘
                       │
                ┌──────▼───────┐         ┌──────────────────┐
                │ dim_counter  │◀────────│ pm_measurements  │
                └──────────────┘         │  (hypertable)    │
                                         └──────────┬───────┘
                                                    │
        ┌──────────────┐         ┌──────────────────▼───────┐
        │ dim_enb      │◀────────│ dim_cell                 │
        └──────────────┘         └──────────────────┬───────┘
                                                    │
              ┌─────────────────────────────────────┼─────────────────┐
              │                                     │                 │
      ┌───────▼────────┐                  ┌─────────▼─────────┐    ┌──▼─────────────┐
      │ fm_alarms      │                  │ cm_changes (SCD2) │    │ anomalies      │
      │ (hypertable)   │                  └───────────────────┘    └────┬───────────┘
      └────────────────┘                                                │
                                                              ┌─────────▼────────┐
                                                              │ incidents        │
                                                              │ (with RCA hyps)  │
                                                              └──────────────────┘
```

## Tables

### Raw (long format)

#### `pm_measurements`
TimescaleDB hypertable partitioned by `ts`.

| Column | Type | Notes |
|---|---|---|
| ts | timestamptz NOT NULL | Measurement interval start |
| enb_id | bigint NOT NULL | FK to dim_enb |
| cell_id | bigint NOT NULL | FK to dim_cell |
| counter_id | int NOT NULL | FK to dim_counter |
| value | double precision | NULL-able (missing measurement vs zero is meaningful) |
| gran_period_seconds | int NOT NULL | Granularity of this measurement (default 3600) |
| PK | (ts, cell_id, counter_id) | |

#### `fm_alarms`
TimescaleDB hypertable partitioned by `raised_at`.

| Column | Type | Notes |
|---|---|---|
| alarm_uid | bigint PK | Surrogate key |
| raised_at | timestamptz NOT NULL | When the alarm was raised |
| cleared_at | timestamptz | NULL if still active |
| enb_id | bigint NOT NULL | FK to dim_enb |
| cell_id | bigint | NULL for eNB-level alarms |
| alarm_type | text NOT NULL | e.g. 'CELL_OUT_OF_SERVICE', 'TRANSPORT_FAILURE' |
| severity | text NOT NULL | 'critical' / 'major' / 'minor' / 'warning' |
| source_system | text | Originating OSS / EMS |
| details | jsonb | Vendor-specific structured detail |

#### `cm_changes` (SCD2 pattern)

| Column | Type | Notes |
|---|---|---|
| change_uid | bigint PK | Surrogate key |
| cell_id | bigint NOT NULL | FK to dim_cell |
| parameter | text NOT NULL | e.g. 'cellIndividualOffset', 'tac' |
| old_value | text | NULL on first-ever set |
| new_value | text NOT NULL | |
| changed_at | timestamptz NOT NULL | |
| changed_by | text | User / system that made the change |

### Dimensions

#### `dim_counter`

| Column | Type | Notes |
|---|---|---|
| counter_id | int PK | Surrogate |
| name | text UNIQUE NOT NULL | Logical name, e.g. 'RRC_CONN_SETUP_SUCC' |
| description | text | Human-readable |
| kpi_group | text | 'accessibility' / 'retainability' / 'mobility' / 'integrity' / 'availability' |
| vendor_id | int | FK to dim_vendor; NULL = vendor-agnostic logical counter |
| vendor_counter_name | text | The vendor's native name |
| technology_id | int | FK to dim_technology |
| unit | text | e.g. 'count', 'seconds', 'kbits' |

#### `dim_cell`

| Column | Type | Notes |
|---|---|---|
| cell_id | bigint PK | Surrogate |
| cell_name | text UNIQUE NOT NULL | Operator's identifier |
| enb_id | bigint NOT NULL | FK to dim_enb |
| sector | int | 1, 2, 3 typical |
| earfcn | int | LTE frequency channel number |
| archetype | text | 'urban_dense' / 'urban' / 'suburban' / 'rural' (used by synth) |
| latitude | double precision | |
| longitude | double precision | |
| azimuth_deg | double precision | |
| created_at | timestamptz NOT NULL | |

#### `dim_enb`

| Column | Type | Notes |
|---|---|---|
| enb_id | bigint PK | |
| enb_name | text UNIQUE NOT NULL | |
| vendor_id | int NOT NULL | FK to dim_vendor |
| region | text | Operational region / cluster |
| site_id | text | Physical site identifier |

#### `dim_vendor`

| Column | Type | Notes |
|---|---|---|
| vendor_id | int PK | |
| vendor_name | text UNIQUE NOT NULL | |

#### `dim_technology`

| Column | Type | Notes |
|---|---|---|
| technology_id | int PK | |
| technology | text UNIQUE NOT NULL | 'LTE' / '5G_NSA' / '5G_SA' |
| release | text | 3GPP release reference |

### Derived (built by dbt)

#### `mart_kpi_cell_hourly`
One row per (cell, hour). All KPIs from `KPI_DEFINITIONS.md` as columns.

#### `mart_kpi_enb_hourly`
Same KPIs aggregated to eNB level.

### Detection and incident layer

#### `anomalies`

| Column | Type | Notes |
|---|---|---|
| anomaly_uid | bigint PK | |
| detected_at | timestamptz NOT NULL | When the detector ran |
| ts | timestamptz NOT NULL | The KPI bucket where the anomaly lives |
| cell_id | bigint NOT NULL | |
| kpi_name | text NOT NULL | e.g. 'rrc_conn_setup_sr' |
| method | text NOT NULL | 'robust_zscore' / 'isolation_forest' / ... |
| score | double precision NOT NULL | Method-specific score |
| severity | text NOT NULL | 'critical' / 'major' / 'minor' / 'info' |
| kpi_value | double precision | The actual KPI value at the time |
| baseline | double precision | Expected value |

#### `incidents`

| Column | Type | Notes |
|---|---|---|
| incident_uid | bigint PK | |
| created_at | timestamptz NOT NULL | |
| anomaly_uid | bigint NOT NULL | FK to anomalies |
| rca_hypotheses | jsonb NOT NULL | Ranked list of {rule_id, confidence, evidence} |
| narrative | text | LLM-generated incident summary |
| status | text NOT NULL | 'open' / 'acknowledged' / 'resolved' / 'false_positive' |

## Indexing strategy

- `pm_measurements`: TimescaleDB hypertable on `ts`, secondary index on
  `(cell_id, counter_id, ts DESC)` for typical analytics queries.
- `fm_alarms`: hypertable on `raised_at`, secondary index on
  `(cell_id, raised_at DESC)`.
- `cm_changes`: index on `(cell_id, changed_at DESC)`.
- Marts: indexed on `(cell_id, ts)`.
- `anomalies`: index on `(cell_id, ts)` and `(detected_at)`.

## Retention

- `pm_measurements`: 90 days at native granularity, downsampled to daily
  beyond that.
- `fm_alarms`: 180 days retained, then archived.
- `cm_changes`: indefinite (small volume, high audit value).
- `anomalies` / `incidents`: indefinite.

Retention is enforced via TimescaleDB retention policies, not via
truncate-and-shrink.
