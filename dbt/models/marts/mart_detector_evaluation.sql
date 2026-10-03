-- mart_detector_evaluation
--
-- Compute TP/FP/FN per detection method against synth_truth ground truth.
-- A detection is a true positive if its (cell, ts) falls within (or
-- within 1 hour of) any injection window on the same cell.

{{ config(materialized='table') }}

with detections as (
    select
        method,
        cell_id,
        ts,
        kpi_name,
        score,
        severity
    from {{ source('analytics', 'anomalies') }}
),

truth as (
    select
        cell_id,
        ts_start,
        ts_end,
        ts_start - interval '1 hour' as ts_start_buffered,
        ts_end + interval '1 hour' as ts_end_buffered,
        pattern_type,
        kpi_affected
    from {{ source('analytics', 'synth_truth') }}
),

detections_labeled as (
    -- Left join: detections that don't match any truth are false positives
    select
        d.method,
        d.cell_id,
        d.ts,
        d.kpi_name,
        d.score,
        d.severity,
        case when t.cell_id is not null then true else false end as is_true_positive,
        t.pattern_type,
        t.kpi_affected
    from detections d
    left join truth t
        on d.cell_id = t.cell_id
        and d.ts between t.ts_start_buffered and t.ts_end_buffered
),

per_method as (
    select
        method,
        count(*) as total_detections,
        count(*) filter (where is_true_positive) as true_positives,
        count(*) filter (where not is_true_positive) as false_positives
    from detections_labeled
    group by method
),

per_method_recall as (
    -- For recall: how many truth events had at least one detection?
    select
        d.method,
        count(distinct (t.cell_id, t.ts_start)) as truth_caught
    from truth t
    inner join detections d
        on d.cell_id = t.cell_id
        and d.ts between t.ts_start_buffered and t.ts_end_buffered
    group by d.method
),

total_truth as (
    select count(*) as total_injections from {{ source('analytics', 'synth_truth') }}
)

select
    pm.method,
    pm.total_detections,
    pm.true_positives,
    pm.false_positives,
    coalesce(pmr.truth_caught, 0) as truth_caught,
    tt.total_injections,

    -- Precision: TP / (TP + FP)
    round(pm.true_positives::numeric / nullif(pm.total_detections, 0), 3)
        as precision,

    -- Recall: caught / total injections
    round(coalesce(pmr.truth_caught, 0)::numeric / nullif(tt.total_injections, 0), 3)
        as recall,

    -- F1: 2 * (P * R) / (P + R)
    round(
        2 * (
            (pm.true_positives::numeric / nullif(pm.total_detections, 0))
            * (coalesce(pmr.truth_caught, 0)::numeric / nullif(tt.total_injections, 0))
        )
        / nullif(
            (pm.true_positives::numeric / nullif(pm.total_detections, 0))
            + (coalesce(pmr.truth_caught, 0)::numeric / nullif(tt.total_injections, 0)),
            0
        ),
        3
    ) as f1_score

from per_method pm
left join per_method_recall pmr on pm.method = pmr.method
cross join total_truth tt
order by pm.method