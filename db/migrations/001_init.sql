-- Cappadocia Balloon Flight Conditions — schema
-- Uses TimescaleDB hypertables for efficient time-series storage.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------------------
-- Reference table: launch sites & nearby aviation reference points.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id           SERIAL PRIMARY KEY,
    slug         TEXT UNIQUE NOT NULL,        -- "goreme", "urgup", "ltaz", ...
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,               -- "launch_site" | "airport"
    icao         TEXT,                        -- only for airports
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    elevation_m  INTEGER,
    notes        TEXT
);

-- ---------------------------------------------------------------------------
-- Hourly forecast (Open-Meteo). One row per (location, model_run, valid_time).
-- model_run lets us keep multiple model issues so we can later study forecast
-- skill (predicted vs. observed).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_hourly (
    location_id          INTEGER NOT NULL REFERENCES locations(id),
    model_run            TIMESTAMPTZ NOT NULL,    -- when the model issued this forecast
    valid_time           TIMESTAMPTZ NOT NULL,    -- the hour being predicted
    source               TEXT NOT NULL,           -- "open-meteo:best_match", etc.

    temperature_2m_c     DOUBLE PRECISION,
    rh_2m_pct            DOUBLE PRECISION,
    dew_point_2m_c       DOUBLE PRECISION,
    pressure_msl_hpa     DOUBLE PRECISION,
    surface_pressure_hpa DOUBLE PRECISION,

    precipitation_mm     DOUBLE PRECISION,
    rain_mm              DOUBLE PRECISION,
    snowfall_cm          DOUBLE PRECISION,

    cloud_cover_pct      DOUBLE PRECISION,
    cloud_cover_low_pct  DOUBLE PRECISION,
    cloud_cover_mid_pct  DOUBLE PRECISION,
    cloud_cover_high_pct DOUBLE PRECISION,
    visibility_m         DOUBLE PRECISION,

    cape_jkg             DOUBLE PRECISION,
    lifted_index         DOUBLE PRECISION,
    boundary_layer_m     DOUBLE PRECISION,

    wind_speed_10m_kmh   DOUBLE PRECISION,
    wind_speed_80m_kmh   DOUBLE PRECISION,
    wind_speed_120m_kmh  DOUBLE PRECISION,
    wind_speed_180m_kmh  DOUBLE PRECISION,
    wind_dir_10m_deg     DOUBLE PRECISION,
    wind_dir_80m_deg     DOUBLE PRECISION,
    wind_dir_120m_deg    DOUBLE PRECISION,
    wind_dir_180m_deg    DOUBLE PRECISION,
    wind_gusts_10m_kmh   DOUBLE PRECISION,

    temperature_80m_c    DOUBLE PRECISION,
    temperature_120m_c   DOUBLE PRECISION,
    temperature_180m_c   DOUBLE PRECISION,

    -- Derived go/no-go score, computed at ingest time.
    flight_score         DOUBLE PRECISION,           -- 0..100
    flight_verdict       TEXT,                        -- GO | MARGINAL | NO_GO
    flight_reasons       TEXT,                        -- comma-separated short reason codes

    inserted_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (location_id, model_run, valid_time)
);

SELECT create_hypertable('forecast_hourly', 'valid_time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS forecast_hourly_loc_valid_idx
    ON forecast_hourly (location_id, valid_time DESC);
CREATE INDEX IF NOT EXISTS forecast_hourly_run_idx
    ON forecast_hourly (model_run DESC);

-- ---------------------------------------------------------------------------
-- Observations from METAR (aviationweather.gov). Airport-tied.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metar_observations (
    location_id     INTEGER NOT NULL REFERENCES locations(id),
    obs_time        TIMESTAMPTZ NOT NULL,
    raw             TEXT NOT NULL,
    temp_c          DOUBLE PRECISION,
    dew_point_c     DOUBLE PRECISION,
    wind_dir_deg    DOUBLE PRECISION,           -- NULL when VRB
    wind_dir_vrb    BOOLEAN DEFAULT FALSE,
    wind_speed_kt   DOUBLE PRECISION,
    wind_gust_kt    DOUBLE PRECISION,
    visibility_m    DOUBLE PRECISION,
    cavok           BOOLEAN DEFAULT FALSE,
    altimeter_hpa   DOUBLE PRECISION,
    flight_cat      TEXT,                       -- VFR | MVFR | IFR | LIFR
    cloud_cover     TEXT,
    cloud_base_ft   INTEGER,
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (location_id, obs_time)
);

SELECT create_hypertable('metar_observations', 'obs_time', if_not_exists => TRUE);

-- ---------------------------------------------------------------------------
-- TAF forecasts (airport terminal forecasts). Stored as the issued bulletin —
-- one row per forecast period.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS taf_forecasts (
    location_id    INTEGER NOT NULL REFERENCES locations(id),
    issue_time     TIMESTAMPTZ NOT NULL,
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_to       TIMESTAMPTZ NOT NULL,
    -- Postgres doesn't allow expressions in PRIMARY KEY, so fcst_change must
    -- be a real (non-null) column. 'BASE' is the implicit value for the first
    -- forecast period in a TAF (no BECMG/TEMPO/FM modifier).
    fcst_change    TEXT NOT NULL DEFAULT 'BASE',
    wind_dir_deg   DOUBLE PRECISION,
    wind_dir_vrb   BOOLEAN DEFAULT FALSE,
    wind_speed_kt  DOUBLE PRECISION,
    wind_gust_kt   DOUBLE PRECISION,
    visibility_m   DOUBLE PRECISION,
    cloud_cover    TEXT,
    cloud_base_ft  INTEGER,
    raw            TEXT,
    inserted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (location_id, issue_time, valid_from, fcst_change)
);

SELECT create_hypertable('taf_forecasts', 'issue_time', if_not_exists => TRUE);

-- ---------------------------------------------------------------------------
-- Daily summary view: collapses each location's day into the sunrise window
-- (typically 04:00–07:00 local) — that's when balloons actually fly.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_sunrise_window AS
SELECT
    f.location_id,
    l.slug AS location_slug,
    l.name AS location_name,
    (f.valid_time AT TIME ZONE 'Europe/Istanbul')::date AS local_date,
    MIN(f.flight_score)         AS min_score,
    AVG(f.flight_score)         AS avg_score,
    MAX(f.wind_speed_10m_kmh)   AS max_wind_10m_kmh,
    MAX(f.wind_gusts_10m_kmh)   AS max_gusts_kmh,
    MIN(f.visibility_m)         AS min_visibility_m,
    MAX(f.precipitation_mm)     AS max_precip_mm,
    MAX(f.cape_jkg)             AS max_cape_jkg,
    BOOL_OR(f.flight_verdict = 'GO')        AS any_go,
    BOOL_AND(f.flight_verdict = 'NO_GO')    AS all_no_go
FROM forecast_hourly f
JOIN locations l ON l.id = f.location_id
WHERE EXTRACT(HOUR FROM f.valid_time AT TIME ZONE 'Europe/Istanbul') BETWEEN 4 AND 7
GROUP BY 1, 2, 3, 4;

-- ---------------------------------------------------------------------------
-- Continuous-aggregate retention helper: keep raw forecasts for 13 months
-- (older data is downsampled). Skip on first run if not enough data yet.
-- ---------------------------------------------------------------------------
SELECT add_retention_policy('forecast_hourly', INTERVAL '395 days', if_not_exists => TRUE);
SELECT add_retention_policy('metar_observations', INTERVAL '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('taf_forecasts', INTERVAL '90 days', if_not_exists => TRUE);
