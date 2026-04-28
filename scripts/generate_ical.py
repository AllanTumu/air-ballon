#!/usr/bin/env python3
"""Generate an iCalendar feed of upcoming morning verdicts.

Reads `v_sunrise_window` from the running TimescaleDB and writes a
`.ics` file (typically to a path served by nginx as static content).

Visitors subscribe to `https://shallweflytomorrow.com/calendar.ics` in
their calendar app and see the next 10 days of HIGH CHANCE / MAYBE /
NO CHANCE mornings as events.

Usage:
    python3 scripts/generate_ical.py [output_path]

Cron-style invocation:
    */15 * * * * cd /home/deploy/air-ballon && \\
        python3 scripts/generate_ical.py /var/www/static/calendar.ics

Dependencies: psycopg (already used by the ingester). Reads DB creds
from the project's `.env` (or the environment if already set).
"""

from __future__ import annotations

import os
import sys
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def load_env(env_path: Path) -> None:
    """Read DB_USER / DB_PASSWORD / DB_NAME from .env, line by line.

    We can't `source` the file because some values contain shell-special
    characters (parens in INGESTER_USER_AGENT). Plain regex is safer.
    """
    if not env_path.exists():
        return
    pattern = re.compile(r"^(DB_USER|DB_PASSWORD|DB_NAME)=(.*)$")
    for raw in env_path.read_text().splitlines():
        m = pattern.match(raw.strip())
        if m and not os.environ.get(m.group(1)):
            os.environ[m.group(1)] = m.group(2)


def fetch_rows(db_user: str, db_name: str) -> list[tuple]:
    """Run psql against the running 'db' compose service and return rows."""
    sql = """
        SELECT
            local_date::text,
            location_slug,
            location_name,
            ROUND(min_score)::int      AS score,
            ROUND(max_wind_10m_kmh)::int AS wind,
            ROUND(max_gusts_kmh)::int  AS gust,
            ROUND(min_visibility_m)::int AS vis_m
        FROM v_sunrise_window
        WHERE local_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '10 days'
          AND location_slug IN ('goreme','cavusin','urgup','uchisar','ortahisar','avanos')
        ORDER BY local_date, location_slug;
    """
    cmd = [
        "docker", "compose", "exec", "-T", "db",
        "psql", "-U", db_user, "-d", db_name,
        "-At", "-F", "|", "-c", sql,
    ]
    out = subprocess.check_output(cmd, text=True)
    rows = []
    for line in out.strip().splitlines():
        if not line or line.startswith("("):
            continue
        parts = line.split("|")
        if len(parts) >= 7:
            rows.append(parts)
    return rows


def verdict_for(score: int) -> tuple[str, str]:
    """Return (label, emoji) for a numeric score."""
    if score >= 70:
        return "HIGH CHANCE", "🎈"
    if score >= 40:
        return "MAYBE", "🌥️"
    return "NO CHANCE", "🚫"


def ical_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def build_calendar(rows: list[tuple]) -> str:
    """Build a Cappadocia-balloon iCal feed."""
    now_utc = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//shallweflytomorrow.com//Cappadocia balloon outlook//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Cappadocia balloon outlook",
        "X-WR-CALDESC:Daily HIGH CHANCE / MAYBE / NO CHANCE verdicts for hot-air balloon flights over Cappadocia.",
        "X-WR-TIMEZONE:Europe/Istanbul",
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]

    # Group rows by date; pick the worst (min score) across launch sites for the day's headline
    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for r in rows:
        by_date[r[0]].append(r)

    for local_date, day_rows in sorted(by_date.items()):
        # Use the BEST score (the most-favourable launch site) for the day-level summary
        best = max(day_rows, key=lambda r: int(r[3]))
        score = int(best[3])
        label, emoji = verdict_for(score)

        # Per-site detail in the description
        details = []
        for r in sorted(day_rows, key=lambda r: -int(r[3])):
            details.append(
                f"{r[2]}: {verdict_for(int(r[3]))[0]} (score {r[3]}, "
                f"wind ≤{r[4]} km/h, gusts ≤{r[5]} km/h, visibility ≥{int(r[6])//1000} km)"
            )
        description = (
            f"Cappadocia balloon outlook for {local_date}.\n\n"
            + "\n".join(details)
            + "\n\nLive dashboard: https://shallweflytomorrow.com\n"
            + "Reminder: this is an unofficial advisory; the operator's go/no-go "
            + "is made each morning at ~04:00 local time."
        )

        # Use a stable UID so subscribers don't accumulate duplicate events.
        uid = f"verdict-{local_date}-{best[1]}@shallweflytomorrow.com"
        ymd = local_date.replace("-", "")

        out.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_utc}",
            f"DTSTART;VALUE=DATE:{ymd}",
            f"SUMMARY:{ical_escape(emoji + ' Balloons over Cappadocia: ' + label)}",
            f"DESCRIPTION:{ical_escape(description)}",
            "URL:https://shallweflytomorrow.com",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ])

    out.append("END:VCALENDAR")
    # iCalendar lines should end with CRLF
    return "\r\n".join(out) + "\r\n"


def main() -> None:
    project_dir = Path(__file__).resolve().parent.parent
    load_env(project_dir / ".env")

    db_user = os.environ.get("DB_USER")
    db_name = os.environ.get("DB_NAME")
    if not (db_user and db_name):
        sys.stderr.write("ERROR: DB_USER / DB_NAME not set (env or .env)\n")
        sys.exit(2)

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else project_dir / "static" / "calendar.ics"

    os.chdir(project_dir)
    rows = fetch_rows(db_user, db_name)
    ics = build_calendar(rows)

    # Write atomically — readers should never see a half-written feed.
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(ics, encoding="utf-8")
    tmp.replace(out_path)

    print(f"[ical] {datetime.now(tz=timezone.utc).isoformat()} wrote {out_path} ({len(rows)} rows -> {len(ics)} bytes)")


if __name__ == "__main__":
    main()
