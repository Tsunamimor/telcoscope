# Architecture Evolution: Why telcoscope Looks the Way It Does

> A short essay on the design choices in this project, framed against typical
> patterns observed in mid-2010s telecoms performance management databases.

## TL;DR

`telcoscope` uses a long-format raw layer with dbt-built wide marts, vendor-agnostic
counter dictionaries, and version-controlled transformations. These choices are
deliberate departures from common mid-2010s industry patterns that worked at the
time but have aged poorly. This document explains why each departure was made.

## The starting point: typical 2010s RAN PM architectures

A representative mid-2010s LTE performance management database — the kind that
RAN performance engineers built routinely against vendor counter feeds — would
typically exhibit the following characteristics:

- **Wide tables per measurement domain.** One table per logical counter group
  (Accessibility, Retainability, Mobility, etc.), each holding 6 key columns
  (network element identifier, cell location, timestamp, granularity period,
  system reference, name) plus tens to hundreds of `[float]` counter columns.
  A complete schema for one vendor's LTE feature set could easily reach 200+
  tables.
- **Vendor-specific counter naming.** Column names mirrored the vendor's
  proprietary identifiers — hex prefixes, internal feature codes, abbreviations
  reflecting that vendor's internal architecture. Counter names from one vendor
  did not align with counter names from another, even when measuring the same
  underlying 3GPP-defined quantity.
- **Parallel raw and aggregate tables.** For every raw 15-minute landing table
  there was a corresponding `A_` aggregate table holding hourly rollups, loaded
  by a stored procedure that did sum/average aggregations.
- **Transformations implemented as stored procedures.** The aggregation logic
  lived in T-SQL stored procedures invoked in dependency order by a master
  procedure, often nightly.
- **Truncate-and-reload housekeeping.** Raw tables truncated after aggregation,
  database periodically shrunk via `DBCC SHRINKDATABASE` or equivalent.
- **No primary keys, no indexes on raw tables.** Heap tables, optimised purely
  for bulk-insert throughput from CSV imports.
- **Reporting via SSRS or similar.** Parameterised stored procedures consumed by
  fixed report layouts; ad-hoc analysis required writing new procedures.

This shape was entirely defensible in its time. SQL Server stored procedures
were the dominant idiom; columnar databases were not yet ubiquitous; dbt did
not exist; cloud-native time-series databases were not widely deployed; CSV
bulk-insert was genuinely the fastest path from vendor counter dump to
queryable data.

## What aged poorly, and why

### Schema rigidity vs vendor introduction

The single most painful consequence of wide-table-per-domain schemas is that
introducing a new vendor — or even a new counter from the existing vendor —
required schema changes. New `CREATE TABLE` statements, new stored procedures
to populate the aggregate counterpart, new joins in every downstream query.
At a network introduction event, the analytics infrastructure became a critical
path item rather than a tool that quietly absorbed change.

A long-format raw layer with a counter dictionary decouples this entirely.
New vendor counters are insert operations on `dim_counter`, not DDL. The same
ingest code, the same dbt models, and the same KPI definitions work
unchanged.

### Vendor counter naming vs operator portfolio reality

Mobile network operators run multi-vendor RAN portfolios. An operator running
two RAN vendors and tracking the same 3GPP-defined Accessibility KPI across
both has historically had to write the KPI calculation twice — once against
each vendor's column naming — and reconcile the results post-hoc. The KPI is
the same 3GPP quantity in both cases; the data should not look fundamentally
different.

A counter dictionary that maps vendor-specific names onto 3GPP-defined logical
counters lets KPI calculations be written once. The mapping table absorbs the
vendor difference; downstream code does not see it. This is a generalisation
of the "semantic layer" pattern that has been mainstream in BI tooling for
decades but has been underused in RAN analytics specifically.

### Stored procedures vs version control

Stored procedures live in the database. Their history is not in git unless
someone deliberately keeps it there. When the same logical KPI calculation
exists in three production environments and a dev environment, there is no
authoritative version. Diffs are difficult. Testing is harder still — there is
no obvious unit-test surface, and integration tests require a live database.

dbt models live in files, are version-controlled by default, support unit and
referential tests as first-class objects, generate documentation and lineage
graphs automatically, and run identically against any compatible database.
The transformation logic becomes review-able by people other than the
original author, which is the precondition for sustained correctness.

### Heap tables and shrink cycles vs time-series workloads

Heap tables with no primary keys made bulk inserts fast, but made every
analytical query slow — the database had no choice but to read everything.
Truncate-and-shrink cycles freed disk space but caused index churn, file
fragmentation, and a recurring source of operational risk.

Time-series-aware engines — TimescaleDB, ClickHouse, DuckDB — partition data
by time at the storage layer. Older data is automatically chunked, optionally
compressed, and selectively dropped via retention policies. Analytical queries
that filter by time touch only the relevant chunks. The operational shape is
fundamentally calmer: ingest stays fast, queries stay fast, retention is
declarative rather than procedural.

### Fixed reports vs analyst self-service

Mid-2010s reporting via SSRS or equivalent assumed a small set of canonical
reports authored by engineering and consumed by operations. Any new question
required engineering to author a new report. Analysts could not easily
explore the data; the report set was the data, effectively.

A modern stack inverts this. dbt-built marts are queryable by anyone with SQL
access. Grafana provides an ops-grade dashboarding surface for canonical views.
Streamlit / Dash / R-Shiny provide analyst-friendly exploration surfaces. The
question "what does this KPI look like for these cells this week" no longer
goes through engineering.

## What carries forward

Several aspects of the mid-2010s pattern are kept deliberately:

- **Hourly aggregation as the reporting grain.** Cell-level 15-minute data is
  too noisy for trend visualisation and too voluminous for cheap storage at
  scale. Hourly is the right default; sub-hourly stays available in the raw
  layer for incident investigation.
- **Separating raw landing from aggregated views.** This is a sound principle;
  what changes is the implementation (dbt models instead of stored procedures).
- **Counter-level granularity in raw.** Aggregating during ingestion loses
  information irreversibly. Keeping raw counters at native granularity preserves
  optionality.
- **Bulk loading for ingestion.** Still the fastest path from CSV / Parquet to
  database. The implementation moves from `BULK INSERT` in T-SQL to Python +
  `COPY` against Postgres, but the principle is the same.

## What this enables that the original could not

- Adding a new vendor: insert rows into `dim_counter`, no DDL
- Adding a new KPI: write a dbt model, no stored procedure deployment
- Comparing the same KPI across two vendors: a single dbt model, joined
  through the counter dictionary
- Testing transformation logic: dbt tests for null-ness, ranges, referential
  integrity, freshness; unit tests for Python code
- Lineage tracing: `dbt docs serve` generates an interactive graph
- Onboarding a new analyst: clone the repo, `make up`, explore the data —
  no DBA approval required, no environment to provision

## What this is not

`telcoscope` is not — and is not trying to be — a production replacement for
a Tier 1 operator's RAN analytics platform. Real operators handle data volumes
several orders of magnitude larger, integrate with OSS/BSS systems we do not
model, and have performance / availability SLAs we make no claim to meet.

What this *is* is a reference implementation of how the same problem class
would be approached in 2026 with modern tooling — small enough to fit on a
laptop, complete enough to demonstrate the design choices, and shaped to
showcase the patterns rather than the scale.
