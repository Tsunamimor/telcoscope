-- mart_kpi_cell_hourly
--
-- One row per (cell, hour). Computes the v1 3GPP KPI set from PM counters
-- using the counter dictionary as the vendor-agnostic abstraction layer.
--
-- This is the canonical KPI mart consumed by Grafana, Streamlit, and the
-- anomaly detection layer.

{{ config(materialized='table') }}

with hourly as (
    select
        date_trunc('hour', m.ts)         as ts,
        m.cell_id,
        c.name                            as counter_name,
        sum(m.value)                      as value
    from {{ ref('stg_pm_measurements') }} m
    inner join {{ source('dims', 'dim_counter') }} c
        on m.counter_id = c.counter_id
    group by 1, 2, 3
),

pivoted as (
    select
        ts,
        cell_id,
        max(case when counter_name = 'RRC_CONN_SETUP_ATT'     then value end) as rrc_conn_setup_att,
        max(case when counter_name = 'RRC_CONN_SETUP_SUCC'    then value end) as rrc_conn_setup_succ,
        max(case when counter_name = 'ERAB_ESTAB_ATT_INIT'    then value end) as erab_estab_att_init,
        max(case when counter_name = 'ERAB_ESTAB_SUCC_INIT'   then value end) as erab_estab_succ_init,
        max(case when counter_name = 'ERAB_ESTAB_ATT_ADDED'   then value end) as erab_estab_att_added,
        max(case when counter_name = 'ERAB_ESTAB_SUCC_ADDED'  then value end) as erab_estab_succ_added,
        max(case when counter_name = 'ERAB_REL_NORMAL_ENB'    then value end) as erab_rel_normal,
        max(case when counter_name = 'ERAB_REL_ABNORMAL_ENB'  then value end) as erab_rel_abnormal,
        max(case when counter_name = 'HO_EXEC_ATT_INTRA_LTE'  then value end) as ho_exec_att_intra_lte,
        max(case when counter_name = 'HO_EXEC_SUCC_INTRA_LTE' then value end) as ho_exec_succ_intra_lte,
        max(case when counter_name = 'PDCP_VOL_DL_DRB'        then value end) as pdcp_vol_dl_drb,
        max(case when counter_name = 'UE_THP_TIME_DL'         then value end) as ue_thp_time_dl,
        max(case when counter_name = 'CELL_DOWNTIME_AUTO'     then value end) as cell_downtime_auto,
        max(case when counter_name = 'CELL_DOWNTIME_MAN'      then value end) as cell_downtime_man
    from hourly
    group by 1, 2
)

select
    ts,
    cell_id,

    -- Accessibility
    case
        when coalesce(rrc_conn_setup_att, 0) = 0 then null
        else rrc_conn_setup_succ::numeric / rrc_conn_setup_att * 100
    end as rrc_conn_setup_sr,

    case
        when coalesce(erab_estab_att_init, 0) + coalesce(erab_estab_att_added, 0) = 0 then null
        else (coalesce(erab_estab_succ_init, 0) + coalesce(erab_estab_succ_added, 0))::numeric
             / (coalesce(erab_estab_att_init, 0) + coalesce(erab_estab_att_added, 0))
             * 100
    end as erab_setup_sr,

    -- Retainability
    case
        when coalesce(erab_rel_normal, 0) + coalesce(erab_rel_abnormal, 0) = 0 then null
        else erab_rel_abnormal::numeric
             / (coalesce(erab_rel_normal, 0) + coalesce(erab_rel_abnormal, 0))
             * 100
    end as erab_drop_rate,

    -- Mobility
    case
        when coalesce(ho_exec_att_intra_lte, 0) = 0 then null
        else ho_exec_succ_intra_lte::numeric / ho_exec_att_intra_lte * 100
    end as intra_lte_ho_sr,

    -- Integrity
    case
        when coalesce(ue_thp_time_dl, 0) = 0 then null
        else pdcp_vol_dl_drb::numeric / ue_thp_time_dl
    end as dl_user_throughput_kbps,

    -- Availability
    (3600 - coalesce(cell_downtime_auto, 0) - coalesce(cell_downtime_man, 0))::numeric
        / 3600 * 100 as cell_availability_pct

from pivoted
