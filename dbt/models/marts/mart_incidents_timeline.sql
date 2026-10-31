{{ config(materialized='view') }}

WITH incidents AS (
    SELECT * FROM {{ source('analytics', 'incidents') }}
),

kpi_at_start AS (
    SELECT i.incident_id,
           k.rrc_conn_setup_sr,
           k.erab_setup_sr,
           k.erab_drop_rate,
           k.intra_lte_ho_sr,
           k.dl_user_throughput_kbps,
           k.cell_availability_pct
    FROM incidents i
    LEFT JOIN {{ ref('mart_kpi_cell_hourly') }} k
      ON k.cell_id = i.cell_id
     AND k.ts = date_trunc('hour', i.ts_start)
),

baseline AS (
    SELECT i.incident_id,
           AVG(k.rrc_conn_setup_sr)       AS baseline_rrc_conn_setup_sr,
           AVG(k.erab_setup_sr)           AS baseline_erab_setup_sr,
           AVG(k.erab_drop_rate)          AS baseline_erab_drop_rate,
           AVG(k.intra_lte_ho_sr)         AS baseline_intra_lte_ho_sr,
           AVG(k.dl_user_throughput_kbps) AS baseline_dl_user_throughput_kbps,
           AVG(k.cell_availability_pct)   AS baseline_cell_availability_pct
    FROM incidents i
    JOIN {{ ref('mart_kpi_cell_hourly') }} k
      ON k.cell_id = i.cell_id
     AND k.ts BETWEEN i.ts_start - INTERVAL '24 hours'
                  AND i.ts_start - INTERVAL '1 hour'
    GROUP BY i.incident_id
)

SELECT i.*,
       k.rrc_conn_setup_sr,
       k.erab_setup_sr,
       k.erab_drop_rate,
       k.intra_lte_ho_sr,
       k.dl_user_throughput_kbps,
       k.cell_availability_pct,

       b.baseline_rrc_conn_setup_sr,
       b.baseline_erab_setup_sr,
       b.baseline_erab_drop_rate,
       b.baseline_intra_lte_ho_sr,
       b.baseline_dl_user_throughput_kbps,
       b.baseline_cell_availability_pct,

       -- Deltas (negative on degradation for success-rate KPIs,
       -- positive on degradation for drop-rate)
       (k.rrc_conn_setup_sr      - b.baseline_rrc_conn_setup_sr)      AS rrc_conn_setup_sr_delta,
       (k.erab_drop_rate         - b.baseline_erab_drop_rate)         AS erab_drop_rate_delta,
       (k.dl_user_throughput_kbps - b.baseline_dl_user_throughput_kbps) AS dl_user_throughput_kbps_delta,
       (k.cell_availability_pct  - b.baseline_cell_availability_pct)  AS cell_availability_pct_delta
FROM incidents i
LEFT JOIN kpi_at_start k USING (incident_id)
LEFT JOIN baseline b     USING (incident_id)