-- Compression policies for time-series tables.
--
-- TimescaleDB stores rows in row-oriented form by default. Once chunks are
-- old enough that no further INSERTs are expected, switching them to columnar
-- compression typically yields 10-20x space savings with negligible read
-- penalty (decompression is transparent).
--
-- Forecast data compresses extremely well because:
--   - location_id repeats across many rows (segment-by candidate)
--   - numeric columns have repeating / smooth values
--
-- Compression policies are idempotent — re-running this migration on an
-- already-compressed-enabled table is a no-op.

-- ---------------------------------------------------------------------------
-- forecast_hourly: enable compression and schedule it for chunks > 14 days.
-- ---------------------------------------------------------------------------
ALTER TABLE forecast_hourly SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'location_id',
    timescaledb.compress_orderby = 'valid_time DESC, model_run DESC'
);

SELECT add_compression_policy(
    'forecast_hourly',
    INTERVAL '14 days',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- metar_observations: compress chunks older than 30 days.
-- ---------------------------------------------------------------------------
ALTER TABLE metar_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'location_id',
    timescaledb.compress_orderby = 'obs_time DESC'
);

SELECT add_compression_policy(
    'metar_observations',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- taf_forecasts: compress chunks older than 14 days. TAFs are short-lived
-- forecasts so compression kicks in quickly.
--
-- Include valid_from and fcst_change in the orderby so TimescaleDB doesn't
-- warn about un-segmented PRIMARY KEY columns. issue_time is the time
-- column; the rest of the PK feeds the orderby.
-- ---------------------------------------------------------------------------
ALTER TABLE taf_forecasts SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'location_id',
    timescaledb.compress_orderby = 'issue_time DESC, valid_from DESC, fcst_change'
);

SELECT add_compression_policy(
    'taf_forecasts',
    INTERVAL '14 days',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- Inspect compression jobs:
--   SELECT * FROM timescaledb_information.jobs
--   WHERE proc_name = 'policy_compression';
--
-- Inspect compression effectiveness once a chunk is compressed:
--   SELECT pg_size_pretty(before_compression_total_bytes) AS before,
--          pg_size_pretty(after_compression_total_bytes) AS after,
--          ROUND(100.0 * after_compression_total_bytes
--                / before_compression_total_bytes, 1) AS pct_kept
--   FROM hypertable_compression_stats('forecast_hourly');
-- ---------------------------------------------------------------------------
