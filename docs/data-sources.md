# Data sources & scoring thresholds

## Sources

### Open-Meteo Forecast API
- Base: `https://api.open-meteo.com/v1/forecast`
- Free, no API key, ~10000 requests/day per IP without registration.
- We pull 10 days × hourly for every launch site.
- Variables we ingest:
  - `temperature_2m`, `relative_humidity_2m`, `dew_point_2m`
  - `precipitation`, `rain`, `snowfall`
  - `pressure_msl`, `surface_pressure`
  - `cloud_cover`, `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high`
  - `visibility`
  - `cape`, `lifted_index`, `boundary_layer_height`
  - `wind_speed_10m`, `wind_speed_80m`, `wind_speed_120m`, `wind_speed_180m`
  - `wind_direction_10m`, `wind_direction_80m`, `wind_direction_120m`, `wind_direction_180m`
  - `wind_gusts_10m`
  - `temperature_80m`, `temperature_120m`, `temperature_180m`
- Source models: ECMWF IFS / ICON / GFS aggregated as "best_match".
- Attribution: data licensed CC BY 4.0.

### Open-Meteo Archive (ERA5)
- Base: `https://archive-api.open-meteo.com/v1/archive`
- ECMWF ERA5 reanalysis. ~5 day delay relative to real time.
- We backfill 90 days on first run; subset of variables (no CAPE, no upper-altitude winds).

### aviationweather.gov
- Base: `https://aviationweather.gov/api/data/metar` and `.../taf`
- Public-domain US NOAA service mirroring global METAR/TAF feeds.
- We pull stations: `LTAZ` (Kapadokya / Nevşehir) and `LTAU` (Kayseri / Erkilet).
- METAR refresh cadence at the station: every 30 min, sometimes more often around departures.

## Scoring thresholds

These map raw weather variables onto a 0–100 score. Tuned conservatively against published commercial balloon ops minima (FAA AC 91-79, BBAC operations manuals, public statements from Cappadocia operators).

| Factor | GO | MARGINAL | NO-GO |
|---|---|---|---|
| Surface wind (10m) | ≤ 12 km/h | 12–18 km/h | ≥ 18 km/h |
| Wind gusts | ≤ 18 km/h | 18–25 km/h | ≥ 25 km/h |
| Gust spread (gust − mean) | < 8 km/h | ≥ 8 km/h | — |
| Visibility | ≥ 5 km | 3–5 km | < 3 km |
| Precipitation | 0 mm | trace | ≥ 0.5 mm/h |
| CAPE | < 200 J/kg | 200–500 J/kg | ≥ 500 J/kg |
| Lifted Index | > 0 | 0 to −2 | ≤ −2 |
| Low cloud cover | < 30% | 30–70% | — (combined with vis) |
| Wind shear (dir 10m vs 80m) | < 60° | 60–120° | ≥ 120° |
| Boundary layer at sunrise | ≥ 50 m | < 50 m | — |

The score starts at 100 and deducts penalties per factor. A NO-GO trigger on any single factor drops the verdict to NO-GO regardless of the numeric score.

### Verdict banding

| Verdict | Score | Meaning |
|---|---|---|
| GO | ≥ 70 and no NO-GO triggers | Conditions look clean — flights probable. |
| MARGINAL | 40–69 | Possible — operators may run with reduced slots; cancellations common. |
| NO-GO | < 40 or any single NO-GO trigger | Cancellation likely. |

## What we deliberately don't model

- **SHGM final authorisation.** This is the actual gate; not public in real time.
- **Landing site availability.** Pilots also need open fields free of livestock or wet crops; not in any feed.
- **Pilot rest / equipment availability** at the operator level.
- **Air traffic slot allocation.** SHGM coordinates ~150 daily slots in peak season.

These are why a `GO` verdict can still result in a cancelled morning. The dashboard claims to predict *weather suitability*, not *operational green-light*.

## Tuning

If you have ground-truth data on cancelled vs. successful mornings, please open an issue. The thresholds were set from desk research; calibrating them against real operator decisions is the highest-value contribution.
