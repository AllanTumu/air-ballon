"""Scrape the Slot Hizmet Merkezi (SHM) page for the official Cappadocia
balloon flight verdict.

Source page (public, anonymous):
    https://shmkapadokya.kapadokya.edu.tr/

The page is run by Kapadokya Üniversitesi on behalf of SHGM (Turkish DGCA)
and publishes the day's authoritative go / no-go call per sector. The
verdict is set manually each morning by the duty meteorologist - there is
no algorithm to replicate. We just scrape what they post.

Polite usage:
  - The page itself meta-refreshes every 100 s. We poll every 10 minutes,
    well below their own cadence.
  - We send a clear User-Agent that names the project and links to the repo.

Page structure (verified by direct inspection 2026-04-29):

  Primary sectors (A, B, C):
      <div class="sector-div"> ...
          <h3>SEKTÖR A UÇULMAZ</h3>          (verdict word in the heading)
          <img src="assets/flags/red-flag.png" />
          ... GÜNCELLEME TARİHİ ve SAATİ : DD.MM.YYYY - HH:MM ...
          ... GEÇERLİ TARİH ve SAATLER : DD.MM.YYYY - HH:MM - HH:MM ...

  Secondary zones (Bölge 2..5):
      <div class="second-left">
          <h4 class="not-fly-black">2.BÖLGE</h4>
          <img src="assets/flags/red-flag.png" />
          ... GÜNCELLEME TARİHİ ve SAATİ : DD.MM.YYYY - HH:MM ...
          ... GEÇERLİ TARİH ve SAATLER : DD.MM.YYYY - HH:MM - HH:MM ...

We don't try to match wrapper closing tags with regex (nested <div>s make
that brittle). Instead we anchor on the heading text, then scan a fixed
window of HTML after it for the flag image and timestamps. This is simple
and resilient to layout tweaks.

All timestamps on the page are local (Europe/Istanbul). We convert to UTC
before storing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog

log = structlog.get_logger(__name__)

URL = "https://shmkapadokya.kapadokya.edu.tr/"
TZ = ZoneInfo("Europe/Istanbul")

# Anchors - primary sector heading or secondary zone heading.
# We capture: (sector letter A|B|C, verdict word) for primary,
# or (None, None, sector number 2..5) for secondary.
_HEADING_RE = re.compile(
    r"<h3[^>]*>\s*SEKT[ÖO]R\s+([ABC])\s+(U[ÇC]ULUR|U[ÇC]ULMAZ)\s*</h3>"
    r"|"
    r"<h4[^>]*>\s*(\d)\.B[ÖO]LGE\s*</h4>",
    re.IGNORECASE,
)

# Inside the window after a heading:
_FLAG_RE = re.compile(r"flags/(red|yellow|green)-flag\.png", re.IGNORECASE)
_GUNCEL_RE = re.compile(
    r"G[ÜU]NCELLEME\s+TAR[İI]H[İI]\s+ve\s+SAAT[İI]"
    r"[\s\S]{0,400}?(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2}):(\d{2})",
    re.IGNORECASE,
)
_GECERLI_RE = re.compile(
    r"GE[ÇC]ERL[İI]\s+TAR[İI]H\s+ve\s+SAATLER"
    r"[\s\S]{0,400}?(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2})",
    re.IGNORECASE,
)

# How far past the heading we read looking for flag + timestamps. Each card
# is ~1.5 KB of HTML, so 3000 chars is comfortably enough but doesn't risk
# spilling into the next card.
_WINDOW_BYTES = 3000


@dataclass(frozen=True)
class SectorVerdict:
    sector: str            # 'A','B','C','2','3','4','5'
    kind: str              # 'primary' | 'secondary'
    flag: str              # 'red' | 'yellow' | 'green'
    verdict: str           # 'UÇULMAZ' | 'UÇULUR'
    issued_at: datetime    # UTC
    valid_from: datetime   # UTC
    valid_to: datetime     # UTC


def _flag_to_verdict(flag: str) -> str:
    """Derive Turkish verdict from flag colour, used for secondary zones
    where the heading does not include a UÇULMAZ/UÇULUR token."""
    return "UÇULUR" if flag == "green" else "UÇULMAZ"


def _normalize_verdict(s: str) -> str:
    s = s.upper()
    # the page uses Turkish UÇULMAZ/UÇULUR; we treat ASCII fallbacks the same
    return s.replace("CULMAZ", "ÇULMAZ").replace("CULUR", "ÇULUR")


def _parse_window(window: str) -> tuple[str, datetime, datetime, datetime] | None:
    """Extract (flag, issued_at, valid_from, valid_to) from a slice of HTML.

    Returns None if any required field is missing.
    """
    flag_m = _FLAG_RE.search(window)
    g = _GUNCEL_RE.search(window)
    v = _GECERLI_RE.search(window)
    if not (flag_m and g and v):
        return None

    flag = flag_m.group(1).lower()
    g_dd, g_mm, g_yyyy, g_h, g_min = (int(x) for x in g.groups())
    v_dd, v_mm, v_yyyy, vf_h, vf_min, vt_h, vt_min = (int(x) for x in v.groups())

    issued_at = datetime(g_yyyy, g_mm, g_dd, g_h, g_min, tzinfo=TZ).astimezone(timezone.utc)
    valid_from = datetime(v_yyyy, v_mm, v_dd, vf_h, vf_min, tzinfo=TZ).astimezone(timezone.utc)
    valid_to = datetime(v_yyyy, v_mm, v_dd, vt_h, vt_min, tzinfo=TZ).astimezone(timezone.utc)
    if valid_to <= valid_from:
        valid_to += timedelta(days=1)

    return flag, issued_at, valid_from, valid_to


def parse_html(html: str) -> list[SectorVerdict]:
    """Extract every sector verdict found on the SHM landing page."""
    out: list[SectorVerdict] = []
    seen: set[tuple[str, str]] = set()

    for m in _HEADING_RE.finditer(html):
        if m.group(1):
            sector = m.group(1).upper()
            kind = "primary"
            heading_verdict = _normalize_verdict(m.group(2))
        elif m.group(3):
            sector = m.group(3)
            kind = "secondary"
            heading_verdict = None  # derived from flag below
        else:
            continue

        window = html[m.end(): m.end() + _WINDOW_BYTES]
        parsed = _parse_window(window)
        if parsed is None:
            log.warning("shm_card_parse_skipped", sector=sector, kind=kind)
            continue

        flag, issued_at, valid_from, valid_to = parsed
        verdict = heading_verdict if heading_verdict else _flag_to_verdict(flag)

        key = (sector, issued_at.isoformat())
        if key in seen:
            continue
        seen.add(key)

        out.append(SectorVerdict(
            sector=sector,
            kind=kind,
            flag=flag,
            verdict=verdict,
            issued_at=issued_at,
            valid_from=valid_from,
            valid_to=valid_to,
        ))
    return out


def fetch(client: httpx.Client) -> list[SectorVerdict]:
    """One scrape pass - returns all parsed verdicts from the live SHM page."""
    log.info("shm_fetch_start", url=URL)
    r = client.get(URL, timeout=15)
    r.raise_for_status()
    verdicts = parse_html(r.text)
    log.info("shm_fetch_done", verdicts=len(verdicts))
    return verdicts
