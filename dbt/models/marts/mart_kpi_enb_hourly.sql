-- mart_kpi_enb_hourly
--
-- One row per (eNB, hour). Same KPI definitions as the cell mart,
-- but computed on eNB-level counter sums.
--
-- Aggregation rule: sum the raw counters up to eNB level FIRST,
-- then apply the KPI formula. Don't average the per-cell KPIs —
-- that would give incorrect weighting (a lightly-loaded cell with
-- a 100% success rate would count equally with a busy one).

{{ config(materialized='table') }}

with enb_agg as (
    select
        ts,
        enb_id,

        sum(rrc_conn_setup_att)     as rrc_conn_setup_att,
        sum(rrc_conn_setup_succ)    as rrc_conn_setup_succ,
        sum(erab_estab_att_init)    as erab_estab_att_init,
        sum(erab_estab_succ_init)   as erab_estab_succ_init,
        sum(erab_estab_att_added)   as erab_estab_att_added,
        sum(erab_estab_succ_added)  as erab_estab_succ_added,
        sum(erab_rel_normal)        as erab_rel_normal,
        sum(erab_rel_abnormal)      as erab_rel_abnormal,
        sum(ho_exec_att_intra_lte)  as ho_exec_att_intra_lte,
        sum(ho_exec_succ_intra_lte) as ho_exec_succ_intra_lte,
        sum(pdcp_vol_dl_drb)        as pdcp_vol_dl_drb,
        sum(ue_thp_time_dl)         as ue_thp_time_dl,
        sum(cell_downtime_auto)     as cell_downtime_auto,
        sum(cell_downtime_man)      as cell_downtime_man,
        count(*)                    as num_cells

    from {{ ref('int_kpi_components_cell_hourly') }}
    group by 1, 2
)

select
    ts,
    enb_id,
    num_cells,

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

    -- Availability — average across cells at eNB
    (3600 * num_cells - coalesce(cell_downtime_auto, 0) - coalesce(cell_downtime_man, 0))::numeric
        / (3600 * num_cells) * 100 as cell_availability_pct

from enb_agg