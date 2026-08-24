-- stg_pm_measurements
--
-- Light cleanup of the raw PM measurements landing table. Casts types,
-- filters out clearly-invalid rows, exposes only the columns downstream
-- models actually need.

{{ config(materialized='view') }}

select
    ts,
    enb_id,
    cell_id,
    counter_id,
    value::double precision as value,
    gran_period_seconds
from {{ source('raw', 'pm_measurements') }}
where ts is not null
  and cell_id is not null
  and counter_id is not null
