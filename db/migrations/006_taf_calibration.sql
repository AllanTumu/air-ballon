-- Calibrate the forecast against the LTAZ TAF.
--
-- Background - see the discussion in docs/calibration.md:
-- Open-Meteo's CAPE / Lifted Index variables routinely under-forecast
-- localised warm-season convection over Cappadocia's terrain. The Turkish
-- State Met aviation forecasters know the local convective patterns, and
-- when they put TS / CB / TCU tokens in the LTAZ TAF they're almost always
-- followed by an SHM red flag. We treat these tokens as a hard cap on our
-- score so we stop over-calling on days the TAF has already flagged.
--
-- We also cap our top score at 85 unconditionally. Even on a perfect
-- forecast day we don't have access to radiosonde / pilot reports / local
-- observations that SHM uses, so claiming 95+ implies a precision we
-- don't have.
--
-- Both changes are applied via VIEW layers on top of the existing
-- _sunrise_window_agg / v_sunrise_window. The raw flight_score in
-- forecast_hourly is left untouched - easy to revisit thresholds without
-- re-ingesting.

-- ---------------------------------------------------------------------------
-- Per-local-date flag: did the LTAZ TAF contain any convective / no-fly
-- token within the operating window 03:00-17:00 Europe/Istanbul?
--
-- Tokens we treat as "TAF says no-fly":
--   * TS, TSRA, TSGR, TSSN, TSPL - thunderstorm of any kind
--   * CB, TCU - cumulonimbus or towering cumulus
--                                   appended to a cloud group like FEW027CB
--
-- We are deliberately permissive - even PROB30 / TEMPO segments count.
-- Aviation forecasters don't put TS/CB in a TAF for fun; if it's in there,
-- the launch window is at material risk.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_taf_day_flags AS
WITH ltaz AS (
    SELECT id FROM locations WHERE icao = 'LTAZ' LIMIT 1
),
days AS (
    SELECT generate_series(
        (CURRENT_DATE - INTERVAL '30 days')::date,
        (CURRENT_DATE + INTERVAL '12 days')::date,
        INTERVAL '1 day'
    )::date AS local_date
)
SELECT
    d.local_date,
    -- Combined flag for any TS/CB/TCU pattern.
    BOOL_OR(t.raw ~* '(\yTS[A-Z]*\y|\d+(CB|TCU)\y)') AS taf_no_fly,
    -- Split flags so the dashboard can show *why* we capped.
    BOOL_OR(t.raw ~* '\yTS[A-Z]*\y')                  AS taf_has_ts,
    BOOL_OR(t.raw ~* '\d+(CB|TCU)\y')                 AS taf_has_cb
FROM days d
LEFT JOIN taf_forecasts t
    ON t.location_id = (SELECT id FROM ltaz)
   AND t.valid_from < ((d.local_date + TIME '17:00') AT TIME ZONE 'Europe/Istanbul')
   AND t.valid_to   > ((d.local_date + TIME '03:00') AT TIME ZONE 'Europe/Istanbul')
GROUP BY d.local_date;

-- ---------------------------------------------------------------------------
-- Calibrated wrapper around v_sunrise_window. Two transformations:
--
--   1. If the TAF flagged convection on the same local_date, cap the
--      min_score at 25 (puts the day firmly in NO CHANCE).
--   2. Cap min_score at 85 in all cases (honest ceiling - we never
--      have enough information to publish 90+).
--
-- We keep the raw score available as raw_min_score for diagnostics and
-- expose taf_no_fly so the dashboard can explain the cap to the user.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_sunrise_window_calibrated AS
SELECT
    w.location_id,
    w.location_slug,
    w.location_name,
    w.local_date,
    LEAST(
        85,
        CASE WHEN COALESCE(f.taf_no_fly, FALSE)
             THEN LEAST(w.min_score, 25)
             ELSE w.min_score
        END
    )                                  AS min_score,
    w.min_score                        AS raw_min_score,
    COALESCE(f.taf_no_fly, FALSE)      AS taf_no_fly,
    COALESCE(f.taf_has_ts, FALSE)      AS taf_has_ts,
    COALESCE(f.taf_has_cb, FALSE)      AS taf_has_cb,
    w.avg_score,
    w.max_wind_10m_kmh,
    w.max_gusts_kmh,
    w.min_visibility_m,
    w.max_precip_mm,
    w.max_cape_jkg,
    w.any_go,
    w.all_no_go
FROM v_sunrise_window w
LEFT JOIN v_taf_day_flags f USING (local_date);
