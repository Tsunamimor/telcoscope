-- telcoscope: initial database setup
-- Runs once when the postgres container is first created.

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Logical schemas (kept thin; the heavy lifting is in dbt models)
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS dims;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA raw IS 'Landing zone for PM / FM / CM data in long format';
COMMENT ON SCHEMA dims IS 'Dimension tables: counters, cells, eNBs, vendors, technology';
COMMENT ON SCHEMA marts IS 'dbt-built KPI marts (vendor-agnostic)';
COMMENT ON SCHEMA analytics IS 'Detection outputs, incidents, analytical scratch';

-- Tables themselves are created by Alembic migrations (see db/migrations/).
-- This script only ensures the extensions and schemas exist.
