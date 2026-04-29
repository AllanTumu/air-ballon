"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_dsn: str
    forecast_interval_min: int   # how often to refresh Open-Meteo forecast
    metar_interval_min: int      # how often to fetch METAR/TAF
    shm_interval_min: int        # how often to scrape the SHM verdict page
    historical_lookback_days: int  # backfill on first run
    user_agent: str
    log_level: str

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            db_dsn=os.environ.get(
                "DB_DSN",
                "postgresql://balloon:balloon@db:5432/balloon",
            ),
            forecast_interval_min=int(os.environ.get("FORECAST_INTERVAL_MIN", "60")),
            metar_interval_min=int(os.environ.get("METAR_INTERVAL_MIN", "15")),
            shm_interval_min=int(os.environ.get("SHM_INTERVAL_MIN", "10")),
            historical_lookback_days=int(os.environ.get("HISTORICAL_LOOKBACK_DAYS", "90")),
            user_agent=os.environ.get(
                "INGESTER_USER_AGENT",
                "cappadocia-balloon-conditions/0.1 (+https://github.com/yourname/air-ballon)",
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
