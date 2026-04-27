"""Ingester entry point.

Schedules:
  • Open-Meteo forecast every FORECAST_INTERVAL_MIN minutes (default 60) for every location.
  • aviationweather.gov METAR every METAR_INTERVAL_MIN minutes (default 15) for airports.
  • aviationweather.gov TAF hourly for airports.
  • One-shot ERA5 historical backfill on startup if the table is sparse.

Each job is wrapped in error handling — a failure in one source must not
silently kill the scheduler.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from apscheduler.schedulers.blocking import BlockingScheduler

import db
from config import Settings
from sources import open_meteo, aviationweather as awc

log = structlog.get_logger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
    )


# --- Forecast job ------------------------------------------------------------

FORECAST_COLS = [
    "location_id", "model_run", "valid_time", "source",
    "temperature_2m_c", "rh_2m_pct", "dew_point_2m_c",
    "pressure_msl_hpa", "surface_pressure_hpa",
    "precipitation_mm", "rain_mm", "snowfall_cm",
    "cloud_cover_pct", "cloud_cover_low_pct", "cloud_cover_mid_pct", "cloud_cover_high_pct",
    "visibility_m", "cape_jkg", "lifted_index", "boundary_layer_m",
    "wind_speed_10m_kmh", "wind_speed_80m_kmh", "wind_speed_120m_kmh", "wind_speed_180m_kmh",
    "wind_dir_10m_deg", "wind_dir_80m_deg", "wind_dir_120m_deg", "wind_dir_180m_deg",
    "wind_gusts_10m_kmh",
    "temperature_80m_c", "temperature_120m_c", "temperature_180m_c",
    "flight_score", "flight_verdict", "flight_reasons",
]


def _upsert_forecast(rows: list[dict], location_id: int) -> int:
    if not rows:
        return 0
    cols = ", ".join(FORECAST_COLS)
    placeholders = ", ".join(["%s"] * len(FORECAST_COLS))
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in FORECAST_COLS
        if c not in ("location_id", "model_run", "valid_time")
    )
    sql = f"""
        INSERT INTO forecast_hourly ({cols})
        VALUES ({placeholders})
        ON CONFLICT (location_id, model_run, valid_time) DO UPDATE SET {updates}
    """
    payload = []
    for r in rows:
        r = {**r, "location_id": location_id}
        payload.append(tuple(r.get(c) for c in FORECAST_COLS))
    with db.conn() as c:
        with c.cursor() as cur:
            cur.executemany(sql, payload)
        c.commit()
    return len(payload)


def job_forecast() -> None:
    started = time.time()
    locations = db.fetch_locations()
    inserted_total = 0
    with httpx.Client(headers={"User-Agent": settings.user_agent}) as client:
        for loc in locations:
            try:
                rows = open_meteo.fetch_forecast(client, loc["latitude"], loc["longitude"], days=10)
                n = _upsert_forecast(rows, loc["id"])
                inserted_total += n
                log.info("forecast_ingested", location=loc["slug"], rows=n)
            except Exception as e:
                log.error("forecast_failed", location=loc["slug"], error=str(e))
    log.info("forecast_job_done", rows=inserted_total, seconds=round(time.time() - started, 1))


# --- METAR / TAF job ---------------------------------------------------------

METAR_COLS = [
    "location_id", "obs_time", "raw", "temp_c", "dew_point_c",
    "wind_dir_deg", "wind_dir_vrb", "wind_speed_kt", "wind_gust_kt",
    "visibility_m", "cavok", "altimeter_hpa", "flight_cat",
    "cloud_cover", "cloud_base_ft",
]
TAF_COLS = [
    "location_id", "issue_time", "valid_from", "valid_to", "fcst_change",
    "wind_dir_deg", "wind_dir_vrb", "wind_speed_kt", "wind_gust_kt",
    "visibility_m", "cloud_cover", "cloud_base_ft", "raw",
]


def _upsert_metar(rows: list[dict], icao_to_id: dict[str, int]) -> int:
    if not rows:
        return 0
    payload = []
    for r in rows:
        loc_id = icao_to_id.get(r["icao"])
        if loc_id is None:
            continue
        rec = {**r, "location_id": loc_id}
        payload.append(tuple(rec.get(c) for c in METAR_COLS))
    if not payload:
        return 0
    cols = ", ".join(METAR_COLS)
    placeholders = ", ".join(["%s"] * len(METAR_COLS))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in METAR_COLS if c not in ("location_id", "obs_time"))
    sql = f"""
        INSERT INTO metar_observations ({cols})
        VALUES ({placeholders})
        ON CONFLICT (location_id, obs_time) DO UPDATE SET {updates}
    """
    with db.conn() as c:
        with c.cursor() as cur:
            cur.executemany(sql, payload)
        c.commit()
    return len(payload)


def _upsert_taf(rows: list[dict], icao_to_id: dict[str, int]) -> int:
    if not rows:
        return 0
    payload = []
    for r in rows:
        loc_id = icao_to_id.get(r["icao"])
        if loc_id is None:
            continue
        rec = {**r, "location_id": loc_id}
        payload.append(tuple(rec.get(c) for c in TAF_COLS))
    if not payload:
        return 0
    cols = ", ".join(TAF_COLS)
    placeholders = ", ".join(["%s"] * len(TAF_COLS))
    sql = f"""
        INSERT INTO taf_forecasts ({cols})
        VALUES ({placeholders})
        ON CONFLICT (location_id, issue_time, valid_from, fcst_change) DO NOTHING
    """
    with db.conn() as c:
        with c.cursor() as cur:
            cur.executemany(sql, payload)
        c.commit()
    return len(payload)


def job_aviation() -> None:
    started = time.time()
    locations = [l for l in db.fetch_locations() if l["kind"] == "airport" and l.get("icao")]
    if not locations:
        return
    icao_to_id = {l["icao"]: l["id"] for l in locations}
    icaos = list(icao_to_id.keys())
    with httpx.Client(headers={"User-Agent": settings.user_agent}) as client:
        try:
            metars = awc.fetch_metars(client, icaos, hours=6)
            n_m = _upsert_metar(metars, icao_to_id)
        except Exception as e:
            log.error("metar_failed", error=str(e))
            n_m = 0
        try:
            tafs = awc.fetch_tafs(client, icaos)
            n_t = _upsert_taf(tafs, icao_to_id)
        except Exception as e:
            log.error("taf_failed", error=str(e))
            n_t = 0
    log.info("aviation_job_done", metars=n_m, tafs=n_t, seconds=round(time.time() - started, 1))


# --- Historical backfill on startup ------------------------------------------

def maybe_backfill() -> None:
    """If forecast_hourly has < 7 days of history per location, kick off
    ERA5 backfill for HISTORICAL_LOOKBACK_DAYS."""
    locations = db.fetch_locations()
    locations = [l for l in locations if l["kind"] == "launch_site"]
    end = datetime.now(tz=timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=settings.historical_lookback_days)

    with httpx.Client(headers={"User-Agent": settings.user_agent}) as client:
        for loc in locations:
            with db.conn() as c:
                row = c.execute(
                    "SELECT COUNT(*) FROM forecast_hourly WHERE location_id = %s AND source = 'open-meteo:era5'",
                    (loc["id"],),
                ).fetchone()
                cnt = row[0] if row else 0
            if cnt > 24 * settings.historical_lookback_days * 0.8:
                log.info("backfill_skip", location=loc["slug"], existing_rows=cnt)
                continue
            try:
                log.info("backfill_start", location=loc["slug"], start=str(start), end=str(end))
                rows = open_meteo.fetch_history(
                    client, loc["latitude"], loc["longitude"], str(start), str(end)
                )
                n = _upsert_forecast(rows, loc["id"])
                log.info("backfill_done", location=loc["slug"], rows=n)
            except Exception as e:
                log.error("backfill_failed", location=loc["slug"], error=str(e))


# --- main --------------------------------------------------------------------

settings: Settings


def main() -> None:
    global settings
    settings = Settings.from_env()
    _setup_logging(settings.log_level)
    log.info("ingester_start", settings={k: v for k, v in settings.__dict__.items() if k != "db_dsn"})

    db.init_pool(settings.db_dsn)

    # First run: prime the database with current data.
    job_forecast()
    job_aviation()
    maybe_backfill()

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(job_forecast, "interval", minutes=settings.forecast_interval_min, id="forecast", max_instances=1)
    sched.add_job(job_aviation, "interval", minutes=settings.metar_interval_min, id="aviation", max_instances=1)

    def _stop(*_):
        log.info("ingester_stop")
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("scheduler_start", forecast_min=settings.forecast_interval_min, metar_min=settings.metar_interval_min)
    sched.start()


if __name__ == "__main__":
    main()
