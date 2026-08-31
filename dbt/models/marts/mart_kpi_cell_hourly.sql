-- mart_kpi_cell_hourly
--
-- One row per (cell, hour). Computes the v1 3GPP KPI set from
-- pre-pivoted counters supplied by int_kpi_components_cell_hourly.

{{ config(materialized='table') }}

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

    -- Availability (3600 sec = 1 hour)
    (3600 - coalesce(cell_downtime_auto, 0) - coalesce(cell_downtime_man, 0))::numeric
        / 3600 * 100 as cell_availability_pct

from {{ ref('int_kpi_components_cell_hourly') }}