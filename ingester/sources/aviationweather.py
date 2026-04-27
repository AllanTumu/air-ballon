"""METAR + TAF client (aviationweather.gov).

Free, no API key. Returns JSON when format=json.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

METAR_URL = "https://aviationweather.gov/api/data/metar"
TAF_URL = "https://aviationweather.gov/api/data/taf"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1.5, min=2, max=20))
def _get_json(client: httpx.Client, url: str, params: dict) -> list[dict]:
    r = client.get(url, params=params, timeout=20)
    r.raise_for_status()
    if not r.text or r.text.strip() == "":
        return []
    return r.json()


def fetch_metars(client: httpx.Client, icaos: Iterable[str], hours: int = 6) -> list[dict]:
    params = {"ids": ",".join(icaos), "format": "json", "hours": hours}
    rows = _get_json(client, METAR_URL, params)
    out: list[dict] = []
    for r in rows:
        out.append({
            "icao": r.get("icaoId"),
            "obs_time": _epoch_to_dt(r.get("obsTime")),
            "raw": r.get("rawOb", ""),
            "temp_c": _f(r.get("temp")),
            "dew_point_c": _f(r.get("dewp")),
            "wind_dir_deg": None if r.get("wdir") == "VRB" else _f(r.get("wdir")),
            "wind_dir_vrb": r.get("wdir") == "VRB",
            "wind_speed_kt": _f(r.get("wspd")),
            "wind_gust_kt": _f(r.get("wgst")),
            "visibility_m": _vis_to_m(r.get("visib")),
            "cavok": r.get("cover") == "CAVOK",
            "altimeter_hpa": _f(r.get("altim")),
            "flight_cat": r.get("fltCat"),
            "cloud_cover": r.get("cover"),
            "cloud_base_ft": _first_cloud_base(r.get("clouds")),
        })
    return out


def fetch_tafs(client: httpx.Client, icaos: Iterable[str]) -> list[dict]:
    params = {"ids": ",".join(icaos), "format": "json"}
    rows = _get_json(client, TAF_URL, params)
    out: list[dict] = []
    for r in rows:
        icao = r.get("icaoId")
        issue = _epoch_to_dt(_to_int_ts(r.get("issueTime")) or r.get("validTimeFrom"))
        for f in r.get("fcsts", []):
            out.append({
                "icao": icao,
                "issue_time": issue,
                "valid_from": _epoch_to_dt(f.get("timeFrom")),
                "valid_to": _epoch_to_dt(f.get("timeTo")),
                "fcst_change": f.get("fcstChange") or "BASE",
                "wind_dir_deg": None if f.get("wdir") == "VRB" else _f(f.get("wdir")),
                "wind_dir_vrb": f.get("wdir") == "VRB",
                "wind_speed_kt": _f(f.get("wspd")),
                "wind_gust_kt": _f(f.get("wgst")),
                "visibility_m": _vis_to_m(f.get("visib")),
                "cloud_cover": (f.get("clouds") or [{}])[0].get("cover"),
                "cloud_base_ft": _first_cloud_base(f.get("clouds")),
                "raw": r.get("rawTAF", ""),
            })
    return out


# --- helpers -----------------------------------------------------------------

def _f(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int_ts(v):
    if isinstance(v, (int, float)):
        return int(v)
    return None


def _epoch_to_dt(v):
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(int(v), tz=timezone.utc)
    return None


def _vis_to_m(v):
    """METAR visibility comes as '6+' (>10km), '9999', or numeric SM/m."""
    if v is None:
        return None
    s = str(v).strip()
    if s.endswith("+"):
        # "6+" means 6+ statute miles ≈ 9999m
        return 9999.0
    try:
        n = float(s)
        # If small (< 100), assume statute miles
        if n < 100:
            return n * 1609.34
        return n
    except ValueError:
        return None


def _first_cloud_base(clouds):
    if not clouds:
        return None
    for c in clouds:
        b = c.get("base")
        if b is not None:
            return int(b)
    return None
