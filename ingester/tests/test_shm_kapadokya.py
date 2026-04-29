"""Unit tests for the SHM scraper.

We check parser behaviour against a tiny HTML fixture. Real upstream tests
are skipped; this layer just locks the parser format so it doesn't regress
silently when the regex is edited.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sources import shm_kapadokya as shm


# Trimmed-down fixture matching the live page structure (verified 2026-04-29).
PRIMARY_NO_FLY = """
<div class="sector-div">
  <div class="row">
    <div class="col-md-6">
      <ul class="sector-list">
        <li class="sector sector-black"><h3>SEKTÖR A UÇULMAZ</h3></li>
        <li class="icon"><img src="assets/flags/red-flag.png"></li>
      </ul>
    </div>
    <div class="col-md-12">
      <ul class="sector-bottom-list">
        <li><h4>GÜNCELLEME TARİHİ ve SAATİ <span>:</span></h4></li>
        <li><h4>29.04.2026 - 07:12</h4></li>
        <li><h4>GEÇERLİ TARİH ve SAATLER <span>:</span></h4></li>
        <li><h4>29.04.2026 - 07:30 - 16:30</h4></li>
      </ul>
    </div>
  </div>
</div>
"""

PRIMARY_FLY = PRIMARY_NO_FLY.replace("UÇULMAZ", "UÇULUR").replace("red-flag", "green-flag")

SECONDARY_BLOCK = """
<div class="second-left">
  <h4 class="not-fly-black">2.BÖLGE</h4>
  <img src="assets/flags/yellow-flag.png" class="img-responsive flag-img">
  <ul class="second-sector-bottom-list">
    <li><h4>GÜNCELLEME TARİHİ ve SAATİ <span>:</span></h4></li>
    <li><h4>29.04.2026 - 07:12</h4></li>
    <li><h4>GEÇERLİ TARİH ve SAATLER <span>:</span></h4></li>
    <li><h4>29.04.2026 - 07:30 - 16:30</h4></li>
  </ul>
</div>
"""


def test_parses_primary_no_fly():
    out = shm.parse_html(PRIMARY_NO_FLY)
    assert len(out) == 1
    v = out[0]
    assert v.sector == "A"
    assert v.kind == "primary"
    assert v.flag == "red"
    assert v.verdict == "UÇULMAZ"


def test_parses_primary_fly_green_flag():
    out = shm.parse_html(PRIMARY_FLY)
    assert len(out) == 1
    v = out[0]
    assert v.flag == "green"
    assert v.verdict == "UÇULUR"


def test_parses_secondary_zone():
    out = shm.parse_html(SECONDARY_BLOCK)
    assert len(out) == 1
    v = out[0]
    assert v.sector == "2"
    assert v.kind == "secondary"
    assert v.flag == "yellow"
    # secondary verdict is derived from flag colour
    assert v.verdict == "UÇULMAZ"


def test_local_time_converted_to_utc():
    """29.04.2026 - 07:12 Europe/Istanbul == 04:12 UTC (UTC+3, no DST)."""
    out = shm.parse_html(PRIMARY_NO_FLY)
    assert out[0].issued_at == datetime(2026, 4, 29, 4, 12, tzinfo=timezone.utc)
    assert out[0].valid_from == datetime(2026, 4, 29, 4, 30, tzinfo=timezone.utc)
    assert out[0].valid_to == datetime(2026, 4, 29, 13, 30, tzinfo=timezone.utc)


def test_handles_combined_page():
    combined = PRIMARY_NO_FLY + PRIMARY_FLY.replace("SEKTÖR A", "SEKTÖR B") + SECONDARY_BLOCK
    out = shm.parse_html(combined)
    assert len(out) == 3
    assert {v.sector for v in out} == {"A", "B", "2"}


def test_returns_empty_on_unrelated_html():
    assert shm.parse_html("<html><body>nothing here</body></html>") == []
