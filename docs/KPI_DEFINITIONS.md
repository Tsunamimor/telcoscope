# KPI Definitions

> 3GPP-aligned KPI definitions implemented by `telcoscope`.
> Primary references: 3GPP TS 32.450 ("Key Performance Indicators (KPI) for
> Evolved Universal Terrestrial Radio Access Network (E-UTRAN); Definitions")
> and TS 32.425 ("Performance measurements; Evolved Universal Terrestrial Radio
> Access Network (E-UTRAN)").

This document is the canonical specification for the KPIs that `telcoscope`
computes. Each KPI lists its 3GPP family, formula, numerator/denominator
counter dependencies, and the dbt model that implements it.

## KPI families (3GPP)

| Family | Intent | Example failure mode |
|---|---|---|
| Accessibility | Can a user connect? | RRC connection setup failures |
| Retainability | Does the connection stay up? | Abnormal E-RAB releases |
| Mobility | Do handovers succeed? | HO preparation / execution failures |
| Integrity | Is the user experience acceptable? | Throughput, latency, packet loss |
| Availability | Is the cell on the air? | Cell unavailable, scheduled / unscheduled |

## v1 KPIs

### 1. RRC Connection Setup Success Rate (Accessibility)

**Family:** Accessibility
**Granularity:** per cell, per hour
**Formula:**

```
RRC_Setup_SR = (Successful RRC connection setups / Attempted RRC connection setups) × 100
```

**Counters (logical names):**
- Numerator: `RRC_CONN_SETUP_SUCC`
- Denominator: `RRC_CONN_SETUP_ATT`

**Healthy range:** ≥ 99.0 % (typical mature LTE network)
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

### 2. E-RAB Setup Success Rate (Accessibility)

**Family:** Accessibility
**Granularity:** per cell, per hour
**Formula:**

```
ERAB_Setup_SR = (Successful E-RAB establishments / Attempted E-RAB establishments) × 100
```

**Counters (logical names):**
- Numerator: `ERAB_ESTAB_SUCC_INIT + ERAB_ESTAB_SUCC_ADDED`
- Denominator: `ERAB_ESTAB_ATT_INIT + ERAB_ESTAB_ATT_ADDED`

**Healthy range:** ≥ 99.0 %
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

### 3. E-RAB Drop Rate (Retainability)

**Family:** Retainability
**Granularity:** per cell, per hour
**Formula:**

```
ERAB_Drop_Rate = (Abnormal E-RAB releases / Normal E-RAB releases + Abnormal E-RAB releases) × 100
```

**Counters (logical names):**
- Numerator: `ERAB_REL_ABNORMAL_ENB`
- Denominator: `ERAB_REL_ABNORMAL_ENB + ERAB_REL_NORMAL_ENB`

**Healthy range:** ≤ 0.5 % (typical; QCI-dependent)
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

### 4. Intra-LTE Handover Success Rate (Mobility)

**Family:** Mobility
**Granularity:** per cell, per hour
**Formula:**

```
Intra_LTE_HO_SR = (Successful intra-LTE handover executions / Attempted intra-LTE handover executions) × 100
```

**Counters (logical names):**
- Numerator: `HO_EXEC_SUCC_INTRA_LTE`
- Denominator: `HO_EXEC_ATT_INTRA_LTE`

**Healthy range:** ≥ 98.0 %
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

### 5. DL User Throughput (Integrity)

**Family:** Integrity
**Granularity:** per cell, per hour
**Formula:**

```
DL_User_Throughput_kbps = (PDCP DL data volume in bits) / (UE active time in seconds)
```

**Counters (logical names):**
- Numerator: `PDCP_VOL_DL_DRB` (kbits)
- Denominator: `UE_THP_TIME_DL` (seconds)

**Healthy range:** highly dependent on RF conditions, spectrum allocation,
loading; baseline established per-cell rather than network-wide.
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

### 6. Cell Availability (Availability)

**Family:** Availability
**Granularity:** per cell, per hour
**Formula:**

```
Cell_Availability_Pct = ((Hour duration − Cell downtime) / Hour duration) × 100
```

**Counters (logical names):**
- Cell downtime = `CELL_DOWNTIME_AUTO + CELL_DOWNTIME_MAN` (seconds)
- Hour duration = 3600 seconds (or summed `GRAN_PERIOD` for partial hours)

**Healthy range:** ≥ 99.9 % (excluding planned maintenance windows)
**Implementation:** `dbt/models/marts/mart_kpi_cell_hourly.sql`

---

## Future KPIs (post-v1)

- E-RAB Drop Rate per QCI (QoS Class Indicator decomposition)
- Inter-RAT handover success rates (LTE ↔ WCDMA, LTE ↔ NR)
- UL User Throughput
- IP Latency
- VoLTE-specific KPIs (CSFB Success Rate, SRVCC Success Rate)
- 5G NR equivalent KPIs (NSA and SA)

## On counter aliasing

The counter logical names above are the names used in `dim_counter.name` for
v1. Vendor-specific identifiers map onto these via `dim_counter.vendor_counter_name`
(or a separate `counter_alias` table — see `docs/DATA_MODEL.md`). KPI dbt models
reference logical names only.
