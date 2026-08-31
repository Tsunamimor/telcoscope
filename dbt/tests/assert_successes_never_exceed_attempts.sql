-- assert_successes_never_exceed_attempts
--
-- Singular test — returns rows that violate the invariant "successes
-- <= attempts". Test passes if zero rows return.

select
    ts,
    cell_id,
    rrc_conn_setup_succ,
    rrc_conn_setup_att,
    'rrc' as which
from {{ ref('int_kpi_components_cell_hourly') }}
where rrc_conn_setup_succ > rrc_conn_setup_att

union all

select
    ts,
    cell_id,
    ho_exec_succ_intra_lte  as rrc_conn_setup_succ,
    ho_exec_att_intra_lte   as rrc_conn_setup_att,
    'ho'  as which
from {{ ref('int_kpi_components_cell_hourly') }}
where ho_exec_succ_intra_lte > ho_exec_att_intra_lte