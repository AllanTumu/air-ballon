"""Postgres connection pool + small helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool
import structlog

log = structlog.get_logger(__name__)

_pool: ConnectionPool | None = None


def init_pool(dsn: str, min_size: int = 1, max_size: int = 4) -> ConnectionPool:
    global _pool
    if _pool is None:
        # Wait for DB to be reachable (compose start-up race).
        for attempt in range(30):
            try:
                with psycopg.connect(dsn, connect_timeout=3) as conn:
                    conn.execute("SELECT 1")
                break
            except Exception as exc:
                log.info("db_not_ready", attempt=attempt, error=str(exc))
                time.sleep(2)
        else:
            raise RuntimeError("Database never came up")
        _pool = ConnectionPool(dsn, min_size=min_size, max_size=max_size, kwargs={"autocommit": False})
    return _pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    if _pool is None:
        raise RuntimeError("Pool not initialised")
    with _pool.connection() as c:
        yield c


def fetch_locations() -> list[dict]:
    """Return all known locations as a list of dicts keyed by column name."""
    sql = (
        "SELECT id, slug, name, kind, icao, latitude, longitude, elevation_m "
        "FROM locations ORDER BY id"
    )
    with conn() as c, c.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
