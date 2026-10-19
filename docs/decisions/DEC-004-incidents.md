# DEC-004 — Incident grouping model

## Status
Accepted — 2026-10-13

## Context
The detections flagged by Week 3  approach land in analytics.anomalies as one row per flag.
Operators measure by network stability by incidents (a time-bounded cluster of events), not rows in a table.
We need to define a grouping model before alerting makes sense.

## Decision
 - Grouping: Group localised event or anomolie detections into incidents keyed by (cell_id, time_window) 
 - Incident lifecycle: Condsider a silence period (2h) threshold as closing an incident. This should be reviewed later based on network activity
 - Incident Priority: Severity is max ranking across the group's detections. Worst case priority would drive attention for action
 - 

## Alternatives considered
- Per-method incidents (statistical and IF kept separate): rejected — 
  this approach could trigger double-notification on the same operational event.
- Fixed 1h windows: rejected — splits long outages artificially.
- Topology-aware grouping (sector-level): deferred to Week 5+.

## Consequences
+ Single incident per real-world event, regardless of how many
  detectors fire.
+ Simple to implement and reason about.
– Won't catch a cascading failure across neighbouring or colocated cells as one
  incident (acceptable for v1).
– The 2h threshold is a guess based on reasonable timeframe and fits within operations shift window;
(this will need calibration against real incident detection data).