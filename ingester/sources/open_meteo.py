"""Open-Meteo client.

Free, no API key, generous rate limits, supports forecast and ERA5
historical reanalysis for full history. Docs: https://open-meteo.com/

We request the union of fields needed for scoring and dashboard panels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from scoring import score_hour

log = structlog.get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "precipitation", "rain", "snowfall",
    "pressure_msl", "surface_pressure",
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "visibility", "cape", "lifted_index", "boundary_layer_height",
    "wind_speed_10m", "wind_speed_80m", "wind_speed_120m", "wind_speed_180m",
    "wind_direction_10m", "wind_direction_80m", "wind_direction_120m", "wind_direction_180m",
    "wind_gusts_10m",
    "temperature_80m", "temperature_120m", "temperature_180m",
]

# Open-Meteo's archive API doesn't support all the same variables; trim.
ARCHIVE_HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "precipitation", "rain", "snowfall",
    "pressure_msl", "surface_pressure",
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "visibility",
    "wind_speed_10m", "wind_speed_100m",
    "wind_direction_10m", "wind_direction_100m",
    "wind_gusts_10m",
]


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1.5, min=2, max=20))
def _get(client: httpx.Client, url: str, params: dict) -> dict:
    r = client.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _row_from_index(payload: dict, hourly_keys: Iterable[str], i: int) -> dict:
    h = payload["hourly"]
    out = {"valid_time": datetime.fromisoformat(h["time"][i]).replace(tzinfo=timezone.utc)}
    # Open-Meteo returns ISO strings without tz when timezone=UTC.
    # We pass timezone=UTC so values are UTC.
    for k in hourly_keys:
        out[k] = h.get(k, [None])[i] if k in h else None
    return out


def fetch_forecast(client: httpx.Client, lat: float, lon: float, days: int = 10) -> list[dict]:
    """Return a list of dicts, one per forecast hour, ready for DB insert."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": days,
        "timezone": "UTC",
    }
    data = _get(client, FORECAST_URL, params)
    model_run = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    return _normalise_forecast(data, model_run, source="open-meteo:best_match")


def fetch_history(client: httpx.Client, lat: float, lon: float, start_date: str, end_date: str) -> list[dict]:
    """Backfill ERA5 reanalysis. Dates 'YYYY-MM-DD'."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(ARCHIVE_HOURLY_VARS),
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }
    data = _get(client, ARCHIVE_URL, params)
    # Archive doesn't have 80/120/180m winds, CAPE, etc. We tag model_run = valid_time
    # so the row is treated as observation-equivalent.
    model_run = datetime.fromisoformat(start_date + "T00:00:00").replace(tzinfo=timezone.utc)
    return _normalise_forecast(data, model_run, source="open-meteo:era5", archive=True)


def _normalise_forecast(payload: dict, model_run: datetime, source: str, archive: bool = False) -> list[dict]:
    h = payload.get("hourly", {})
    times = h.get("time", [])
    out: list[dict] = []
    for i, t in enumerate(times):
        # Open-Meteo timestamps without tz when timezone=UTC.
        valid = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        row = {
            "model_run": model_run,
            "valid_time": valid,
            "source": source,
            "temperature_2m_c": _at(h, "temperature_2m", i),
            "rh_2m_pct": _at(h, "relative_humidity_2m", i),
            "dew_point_2m_c": _at(h, "dew_point_2m", i),
            "pressure_msl_hpa": _at(h, "pressure_msl", i),
            "surface_pressure_hpa": _at(h, "surface_pressure", i),
            "precipitation_mm": _at(h, "precipitation", i),
            "rain_mm": _at(h, "rain", i),
            "snowfall_cm": _at(h, "snowfall", i),
            "cloud_cover_pct": _at(h, "cloud_cover", i),
            "cloud_cover_low_pct": _at(h, "cloud_cover_low", i),
            "cloud_cover_mid_pct": _at(h, "cloud_cover_mid", i),
            "cloud_cover_high_pct": _at(h, "cloud_cover_high", i),
            "visibility_m": _at(h, "visibility", i),
            "cape_jkg": _at(h, "cape", i),
            "lifted_index": _at(h, "lifted_index", i),
            "boundary_layer_m": _at(h, "boundary_layer_height", i),
            "wind_speed_10m_kmh": _at(h, "wind_speed_10m", i),
            "wind_speed_80m_kmh": _at(h, "wind_speed_80m", i) if not archive else _at(h, "wind_speed_100m", i),
            "wind_speed_120m_kmh": _at(h, "wind_speed_120m", i),
            "wind_speed_180m_kmh": _at(h, "wind_speed_180m", i),
            "wind_dir_10m_deg": _at(h, "wind_direction_10m", i),
            "wind_dir_80m_deg": _at(h, "wind_direction_80m", i) if not archive else _at(h, "wind_direction_100m", i),
            "wind_dir_120m_deg": _at(h, "wind_direction_120m", i),
            "wind_dir_180m_deg": _at(h, "wind_direction_180m", i),
            "wind_gusts_10m_kmh": _at(h, "wind_gusts_10m", i),
            "temperature_80m_c": _at(h, "temperature_80m", i),
            "temperature_120m_c": _at(h, "temperature_120m", i),
            "temperature_180m_c": _at(h, "temperature_180m", i),
        }
        result = score_hour(row)
        row["flight_score"] = result.score
        row["flight_verdict"] = result.verdict
        row["flight_reasons"] = result.reasons_str()
        out.append(row)
    return out


def _at(h: dict, key: str, i: int):
    arr = h.get(key)
    if not arr or i >= len(arr):
        return None
    return arr[i]
