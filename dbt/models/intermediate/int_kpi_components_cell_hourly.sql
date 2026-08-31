-- int_kpi_components_cell_hourly
--
-- Pivots the long-format PM measurements into one row per (cell, hour)
-- with all 14 counter values as columns. This is the shared
-- pre-aggregated substrate for both the cell-level and eNB-level KPI
-- marts.
--
-- Materialised as a table (not ephemeral) because we materialise it
-- once and re-use it in two marts — cheaper than compiling the pivot
-- into both callers.

{{ config(
    materialized='table',
    indexes=[
      {'columns': ['ts', 'cell_id'], 'unique': True},
      {'columns': ['ts']},
    ]
) }}

with hourly as (
    select
        date_trunc('hour', m.ts) as ts,
        m.cell_id,
        m.enb_id,
        c.name                    as counter_name,
        sum(m.value)              as value
    from {{ ref('stg_pm_measurements') }} m
    inner join {{ source('dims', 'dim_counter') }} c
        on m.counter_id = c.counter_id
    group by 1, 2, 3, 4
)

select
    ts,
    cell_id,
    enb_id,

    -- Accessibility counters
    max(case when counter_name = 'RRC_CONN_SETUP_ATT'     then value end) as rrc_conn_setup_att,
    max(case when counter_name = 'RRC_CONN_SETUP_SUCC'    then value end) as rrc_conn_setup_succ,
    max(case when counter_name = 'ERAB_ESTAB_ATT_INIT'    then value end) as erab_estab_att_init,
    max(case when counter_name = 'ERAB_ESTAB_SUCC_INIT'   then value end) as erab_estab_succ_init,
    max(case when counter_name = 'ERAB_ESTAB_ATT_ADDED'   then value end) as erab_estab_att_added,
    max(case when counter_name = 'ERAB_ESTAB_SUCC_ADDED'  then value end) as erab_estab_succ_added,

    -- Retainability counters
    max(case when counter_name = 'ERAB_REL_NORMAL_ENB'    then value end) as erab_rel_normal,
    max(case when counter_name = 'ERAB_REL_ABNORMAL_ENB'  then value end) as erab_rel_abnormal,

    -- Mobility counters
    max(case when counter_name = 'HO_EXEC_ATT_INTRA_LTE'  then value end) as ho_exec_att_intra_lte,
    max(case when counter_name = 'HO_EXEC_SUCC_INTRA_LTE' then value end) as ho_exec_succ_intra_lte,

    -- Integrity counters
    max(case when counter_name = 'PDCP_VOL_DL_DRB'        then value end) as pdcp_vol_dl_drb,
    max(case when counter_name = 'UE_THP_TIME_DL'         then value end) as ue_thp_time_dl,

    -- Availability counters
    max(case when counter_name = 'CELL_DOWNTIME_AUTO'     then value end) as cell_downtime_auto,
    max(case when counter_name = 'CELL_DOWNTIME_MAN'      then value end) as cell_downtime_man

from hourly
group by 1, 2, 3