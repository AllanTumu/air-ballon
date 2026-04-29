-- Convert v_sunrise_window from a regular view into a TimescaleDB
-- continuous aggregate. Same column shape as before, so the dashboard
-- queries don't have to change.
--
-- A continuous aggregate is a materialized view that TimescaleDB
-- refreshes incrementally as new data arrives. The "Daily sunrise-window
-- verdict" panel and "Historical morning GO rate" panel will hit
-- pre-computed rows instead of scanning the raw forecast_hourly table.
--
-- At 8 locations × 365 days = ~2,920 rows total — versus millions of raw
-- forecast rows — queries are essentially constant-time.

-- ---------------------------------------------------------------------------
-- Drop the old plain view first (continuous aggregates can't share names
-- with existing relations). DO NOT drop on subsequent runs — that would
-- needlessly invalidate dependent objects.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'v_sunrise_window' AND c.relkind = 'v'
          AND n.nspname = current_schema()
    ) AND NOT EXISTS (
        SELECT 1 FROM timescaledb_information.continuous_aggregates
        WHERE view_name = '_sunrise_window_agg'
    ) THEN
        DROP VIEW v_sunrise_window;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- The raw continuous aggregate. We bucket by day in Istanbul time directly
-- using TimescaleDB's timezone-aware time_bucket.
--
-- Continuous aggregates have restrictions on what they can SELECT — no
-- joins, no subqueries, no non-immutable functions on the input. So we
-- aggregate just the numeric columns from forecast_hourly here, then join
-- to `locations` in a thin wrapper view below.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS _sunrise_window_agg
WITH (timescaledb.continuous) AS
SELECT
    location_id,
    time_bucket(INTERVAL '1 day', valid_time, 'Europe/Istanbul') AS day_bucket,
    MIN(flight_score)             AS min_score,
    AVG(flight_score)             AS avg_score,
    MAX(wind_speed_10m_kmh)       AS max_wind_10m_kmh,
    MAX(wind_gusts_10m_kmh)       AS max_gusts_kmh,
    MIN(visibility_m)             AS min_visibility_m,
    MAX(precipitation_mm)         AS max_precip_mm,
    MAX(cape_jkg)                 AS max_cape_jkg,
    BOOL_OR(flight_verdict = 'GO')        AS any_go,
    BOOL_AND(flight_verdict = 'NO_GO')    AS all_no_go
FROM forecast_hourly
WHERE EXTRACT(HOUR FROM valid_time AT TIME ZONE 'Europe/Istanbul') BETWEEN 4 AND 7
GROUP BY 1, 2
WITH NO DATA;

-- ---------------------------------------------------------------------------
-- Refresh policy: re-aggregate the trailing 90 days every hour, with a 1-hour
-- guard so we don't try to aggregate the bucket currently being filled.
-- ---------------------------------------------------------------------------
SELECT add_continuous_aggregate_policy(
    '_sunrise_window_agg',
    start_offset => INTERVAL '90 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Backfill once now so the dashboard isn't empty until the policy first runs.
CALL refresh_continuous_aggregate('_sunrise_window_agg', NULL, NULL);

-- ---------------------------------------------------------------------------
-- Public-facing wrapper view that joins to `locations` and exposes a
-- `local_date` column the dashboard already queries.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_sunrise_window AS
SELECT
    a.location_id,
    l.slug                              AS location_slug,
    l.name                              AS location_name,
    (a.day_bucket AT TIME ZONE 'Europe/Istanbul')::date AS local_date,
    a.min_score,
    a.avg_score,
    a.max_wind_10m_kmh,
    a.max_gusts_kmh,
    a.min_visibility_m,
    a.max_precip_mm,
    a.max_cape_jkg,
    a.any_go,
    a.all_no_go
FROM _sunrise_window_agg a
JOIN locations l ON l.id = a.location_id;

-- ---------------------------------------------------------------------------
-- Inspect:
--   SELECT * FROM timescaledb_information.continuous_aggregates;
--   SELECT * FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate';
-- ---------------------------------------------------------------------------
