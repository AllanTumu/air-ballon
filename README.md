# Cappadocia Balloon Flight Conditions

[![CI](https://github.com/AllanTumu/air-ballon/actions/workflows/ci.yml/badge.svg)](https://github.com/AllanTumu/air-ballon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/AllanTumu/air-ballon?display_name=tag&sort=semver)](https://github.com/AllanTumu/air-ballon/releases)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

A community-maintained, open-source Grafana dashboard that tells you whether hot-air balloons are likely to fly over Göreme tomorrow morning — and over the next 10 days.

Inspired by the Northern Lights aurora dashboard shown at Grafana Conference 2026 Barcelona, and built after one too many people (including the author) flew across the world for a Cappadocia balloon ride only to be cancelled at sunrise.

## Contents

- [What it does](#what-it-does)
- [Stack](#stack)
- [Data sources](#data-sources)
- [Quick start (local)](#quick-start-local)
- [Deploy to DigitalOcean](#deploy-to-digitalocean)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Credits](#credits)

## What it does

- Pulls forecasts and observations from open sources every 15–60 minutes.
- Computes a **flight likelihood score** (0–100) for every hour at every launch site, with a **GO / MARGINAL / NO-GO** verdict.
- Surfaces the underlying weather factors so you can see *why* a morning is likely to fly or not — wind speed at four altitudes, gusts, visibility, CAPE, lifted index, cloud ceiling, precipitation, boundary layer height.
- Shows a 10-day outlook for every launch site (Göreme, Çavuşin, Uçhisar, Ortahisar, Ürgüp, Avanos).
- Tracks live METAR and TAF from Kapadokya (LTAZ) and Kayseri (LTAU) airports.
- Keeps history so you can study the seasonal pattern and check forecast accuracy after the fact.

This is **advisory**. The actual go/no-go is made by Turkey's Directorate General of Civil Aviation (SHGM) in coordination with operators each morning around 04:00–05:00 local. Cancellation can happen even on green-numbers mornings; flights can occasionally launch on yellow ones. Use this to plan, not as a guarantee.

## Stack

- **TimescaleDB** (Postgres extension) for time-series storage with retention policies.
- **Python ingester** (httpx + APScheduler + tenacity) with a fetcher per data source.
- **Grafana OSS** with anonymous viewer access for public read-only dashboards.
- **nginx** + Let's Encrypt for HTTPS.
- **Docker Compose** so the whole thing is one command.

## Data sources

All free, all public, no API keys.

| Source | What it provides | Refresh |
|---|---|---|
| [Open-Meteo Forecast](https://open-meteo.com/en/docs) | 10-day hourly forecast: wind at 10/80/120/180m, gusts, CAPE, lifted index, visibility, cloud layers, precipitation, boundary layer height | 60 min |
| [Open-Meteo Archive](https://open-meteo.com/en/docs/historical-weather-api) | ERA5 reanalysis for full historical backfill | One-shot on first run |
| [aviationweather.gov](https://aviationweather.gov/data/api/) | METAR + TAF for LTAZ + LTAU | 15 min |

The scoring thresholds are documented in [`docs/data-sources.md`](docs/data-sources.md) and inline in `ingester/scoring.py`.

## Quick start (local)

```bash
git clone https://github.com/AllanTumu/air-ballon.git
cd air-ballon
cp .env.example .env
# Edit .env — at minimum change the DB and Grafana passwords.
docker compose up -d --build
```

Wait ~30 seconds for the first ingest, then open http://localhost:3030 (or whatever you set `GRAFANA_HOST_PORT` to in `.env`). Anonymous viewers see the dashboard; sign in as the admin user from `.env` to edit.

Run the unit tests:

```bash
make test
```

## Deploy to DigitalOcean

See [DEPLOY.md](DEPLOY.md) for a step-by-step guide.

The short version: provision a basic 2 GB / 1 vCPU droplet (Ubuntu 22.04), point a DNS A record at it, copy this repo over, fill in `.env`, run `docker compose up -d`, then `make certbot DOMAIN=your.domain EMAIL=you@example.com` and uncomment the HTTPS server block in `nginx/nginx.conf`.

## Repository layout

```
air-ballon/
├── docker-compose.yml       # full stack
├── .env.example             # config — copy to .env
├── Makefile                 # convenience commands
├── ARCHITECTURE.md          # system design walk-through
├── CONTRIBUTING.md          # how to contribute
├── CHANGELOG.md             # what changed when
├── SECURITY.md              # vulnerability disclosure
├── CODE_OF_CONDUCT.md       # community standards
├── ingester/                # Python data fetchers + scoring
│   ├── main.py              # APScheduler entrypoint
│   ├── scoring.py           # GO / MARGINAL / NO-GO logic
│   ├── sources/
│   │   ├── open_meteo.py
│   │   └── aviationweather.py
│   └── tests/
├── db/migrations/           # SQL schema, runs on first DB boot
├── grafana/
│   ├── provisioning/        # auto-loaded datasource + dashboard provider
│   └── dashboards/          # the dashboard JSON
├── nginx/                   # reverse proxy + TLS
├── docs/                    # data sources, thresholds, releases
└── .github/                 # issue + PR templates, CI/release workflows
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, data flow, scoring logic, deployment topology.
- [DEPLOY.md](DEPLOY.md) — DigitalOcean deployment walkthrough.
- [CONTRIBUTING.md](CONTRIBUTING.md) — branching, commits, PR flow, code style.
- [docs/data-sources.md](docs/data-sources.md) — every weather variable used and the scoring thresholds.
- [docs/releases.md](docs/releases.md) — versioning, release process, rollback.
- [CHANGELOG.md](CHANGELOG.md) — what changed in each release.
- [SECURITY.md](SECURITY.md) — vulnerability disclosure.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards.

## Contributing

If you live in Cappadocia, work for an operator, or have ridden balloons there and noticed the dashboard's score doesn't match what actually happened, please open an issue. Especially valuable:

- Calibrating the wind / gust thresholds against actual operator practice.
- Adding launch sites we missed.
- Adding satellite-derived fog detection.
- Translating the dashboard text to Turkish.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

## License

MIT — see [LICENSE](LICENSE).

## Credits

- Forecast data © Open-Meteo (CC BY 4.0).
- METAR/TAF data from the FAA Aviation Weather Center (public domain).
- Inspired by the Northern Lights aurora dashboard shown at Grafana Conference 2026 Barcelona.
