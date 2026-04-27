"""Flight-likelihood scoring for hot-air balloon operations.

Translates a single forecast hour into a 0-100 score plus a verdict
(GO / MARGINAL / NO_GO) and human-readable reasons.

Thresholds are conservative and based on commercial balloon ops practice:
- Surface wind > ~10 kt (18 km/h) is widely considered a hard no-go for
  passenger balloons (FAA AC 91-79, BBAC ops manuals, operator guidance
  from Cappadocia operators including Royal Balloon and Voyager).
- Gust spread > 8 km/h is a launch hazard even when mean wind is acceptable.
- Visibility minima of 3 km / cloud ceiling 1000 ft AGL come from VFR
  ballooning rules in most jurisdictions.
- CAPE > 500 J/kg and LI < -2 indicate convective risk; never fly under or
  near developing thunderstorms.
- Precipitation: any measurable rain/snow grounds a passenger flight.

These are *advisory* — the local SHGM authorisation, the pilot's go/no-go,
and the operator's own minima are the real decision. This is a
weather-likelihood tool, not flight authorisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --- Thresholds (tuneable via env later) -------------------------------------

WIND_GO_KMH         = 12.0   # green ceiling
WIND_MARGINAL_KMH   = 18.0   # marginal ceiling; above = NO-GO
GUST_GO_KMH         = 18.0
GUST_MARGINAL_KMH   = 25.0
GUST_SPREAD_MARGINAL = 8.0   # gust - mean wind
VIS_GO_M            = 5000.0
VIS_MARGINAL_M      = 3000.0
PRECIP_GO_MM        = 0.0    # any precipitation drops score
PRECIP_NOGO_MM      = 0.5
CAPE_GO_JKG         = 200.0
CAPE_NOGO_JKG       = 500.0
LI_GO               = 0.0
LI_NOGO             = -2.0
CLOUD_LOW_GO_PCT    = 30.0
CLOUD_LOW_MARGINAL_PCT = 70.0
WIND_SHEAR_DIR_MARGINAL_DEG = 60.0  # 10m vs 80m direction delta
WIND_SHEAR_DIR_NOGO_DEG     = 120.0
WIND_SHEAR_SPD_MARGINAL_KMH = 15.0  # 10m vs 80m speed delta

GO_SCORE_MIN        = 70.0
MARGINAL_SCORE_MIN  = 40.0


@dataclass
class ScoreResult:
    score: float
    verdict: str           # GO | MARGINAL | NO_GO
    reasons: list[str] = field(default_factory=list)

    def reasons_str(self) -> str:
        return ",".join(self.reasons)


def _angle_diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def score_hour(row: dict) -> ScoreResult:
    """Score a single forecast hour. `row` must contain Open-Meteo-style keys.

    Returns a ScoreResult. Designed to be safe against missing fields —
    missing data is logged as 'unknown_X' rather than counted against the score.
    """
    score = 100.0
    reasons: list[str] = []

    # --- WIND (most important) ----------------------------------------------
    wind = row.get("wind_speed_10m_kmh")
    if wind is not None:
        if wind >= WIND_MARGINAL_KMH:
            score -= 60
            reasons.append(f"wind_high_{wind:.0f}kmh")
        elif wind >= WIND_GO_KMH:
            score -= 25
            reasons.append(f"wind_marginal_{wind:.0f}kmh")
    else:
        reasons.append("unknown_wind")

    # --- GUSTS ---------------------------------------------------------------
    gust = row.get("wind_gusts_10m_kmh")
    if gust is not None:
        if gust >= GUST_MARGINAL_KMH:
            score -= 35
            reasons.append(f"gusts_high_{gust:.0f}kmh")
        elif gust >= GUST_GO_KMH:
            score -= 12
            reasons.append(f"gusts_marginal_{gust:.0f}kmh")
        if wind is not None and (gust - wind) >= GUST_SPREAD_MARGINAL:
            score -= 10
            reasons.append(f"gust_spread_{(gust - wind):.0f}kmh")

    # --- WIND SHEAR (10m vs 80m) --------------------------------------------
    dir_diff = _angle_diff(row.get("wind_dir_10m_deg"), row.get("wind_dir_80m_deg"))
    if dir_diff is not None:
        if dir_diff >= WIND_SHEAR_DIR_NOGO_DEG:
            score -= 20
            reasons.append(f"shear_dir_{dir_diff:.0f}deg")
        elif dir_diff >= WIND_SHEAR_DIR_MARGINAL_DEG:
            score -= 8
            reasons.append(f"shear_dir_{dir_diff:.0f}deg")

    spd80 = row.get("wind_speed_80m_kmh")
    if wind is not None and spd80 is not None:
        delta = abs(spd80 - wind)
        if delta >= WIND_SHEAR_SPD_MARGINAL_KMH:
            score -= 8
            reasons.append(f"shear_spd_{delta:.0f}kmh")

    # --- VISIBILITY ---------------------------------------------------------
    vis = row.get("visibility_m")
    if vis is not None:
        if vis < VIS_MARGINAL_M:
            score -= 50
            reasons.append(f"vis_low_{vis:.0f}m")
        elif vis < VIS_GO_M:
            score -= 15
            reasons.append(f"vis_marginal_{vis:.0f}m")

    # --- PRECIPITATION ------------------------------------------------------
    precip = row.get("precipitation_mm")
    if precip is not None:
        if precip >= PRECIP_NOGO_MM:
            score -= 60
            reasons.append(f"precip_{precip:.1f}mm")
        elif precip > PRECIP_GO_MM:
            score -= 15
            reasons.append(f"precip_trace_{precip:.1f}mm")

    # --- CONVECTIVE ---------------------------------------------------------
    cape = row.get("cape_jkg")
    if cape is not None:
        if cape >= CAPE_NOGO_JKG:
            score -= 50
            reasons.append(f"cape_high_{cape:.0f}")
        elif cape >= CAPE_GO_JKG:
            score -= 12
            reasons.append(f"cape_elev_{cape:.0f}")

    li = row.get("lifted_index")
    if li is not None:
        if li <= LI_NOGO:
            score -= 30
            reasons.append(f"lifted_index_{li:.1f}")
        elif li <= LI_GO:
            score -= 8
            reasons.append(f"lifted_index_{li:.1f}")

    # --- CLOUD CEILING (low cloud) ------------------------------------------
    cloud_low = row.get("cloud_cover_low_pct")
    if cloud_low is not None:
        if cloud_low >= CLOUD_LOW_MARGINAL_PCT:
            score -= 12
            reasons.append(f"low_cloud_{cloud_low:.0f}pct")
        elif cloud_low >= CLOUD_LOW_GO_PCT:
            score -= 4
            reasons.append(f"low_cloud_{cloud_low:.0f}pct")

    # --- INVERSION HINT (boundary layer very low) ---------------------------
    blh = row.get("boundary_layer_m")
    if blh is not None and blh < 50:
        score -= 6
        reasons.append(f"shallow_blh_{blh:.0f}m")

    score = max(0.0, min(100.0, score))

    if score >= GO_SCORE_MIN and not any(r.startswith(("wind_high", "gusts_high", "vis_low", "precip_", "cape_high")) for r in reasons):
        verdict = "GO"
    elif score >= MARGINAL_SCORE_MIN:
        verdict = "MARGINAL"
    else:
        verdict = "NO_GO"

    return ScoreResult(score=round(score, 1), verdict=verdict, reasons=reasons)


# --- Convenience -------------------------------------------------------------

def explain(result: ScoreResult) -> str:
    """Render a short human-friendly explanation."""
    if not result.reasons:
        return f"{result.verdict} ({result.score:.0f}) — clean conditions."
    return f"{result.verdict} ({result.score:.0f}) — {'; '.join(result.reasons)}"


if __name__ == "__main__":
    # Sanity demo
    samples = [
        ("calm dawn", dict(wind_speed_10m_kmh=4, wind_gusts_10m_kmh=8, wind_speed_80m_kmh=5,
                            wind_dir_10m_deg=140, wind_dir_80m_deg=145,
                            visibility_m=40000, precipitation_mm=0, cape_jkg=0,
                            lifted_index=4, cloud_cover_low_pct=0, boundary_layer_m=200)),
        ("windy", dict(wind_speed_10m_kmh=22, wind_gusts_10m_kmh=35, wind_speed_80m_kmh=28,
                       wind_dir_10m_deg=180, wind_dir_80m_deg=200,
                       visibility_m=30000, precipitation_mm=0, cape_jkg=0,
                       lifted_index=3, cloud_cover_low_pct=10, boundary_layer_m=400)),
        ("foggy", dict(wind_speed_10m_kmh=2, wind_gusts_10m_kmh=4, wind_speed_80m_kmh=3,
                       wind_dir_10m_deg=10, wind_dir_80m_deg=20,
                       visibility_m=1500, precipitation_mm=0, cape_jkg=0,
                       lifted_index=5, cloud_cover_low_pct=95, boundary_layer_m=20)),
        ("storm", dict(wind_speed_10m_kmh=8, wind_gusts_10m_kmh=14, wind_speed_80m_kmh=10,
                       wind_dir_10m_deg=200, wind_dir_80m_deg=210,
                       visibility_m=8000, precipitation_mm=2.0, cape_jkg=900,
                       lifted_index=-3, cloud_cover_low_pct=80, boundary_layer_m=300)),
    ]
    for label, row in samples:
        r = score_hour(row)
        print(f"{label:>10}: {explain(r)}")
