# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Version numbers are tagged in git as `vX.Y.Z`. Breaking changes bump MAJOR; new dashboard panels or new data sources bump MINOR; threshold tweaks, bug fixes, and doc changes bump PATCH.

## [Unreleased]

### Added
- `ARCHITECTURE.md` — full system design walk-through with sequence diagrams.
- `CONTRIBUTING.md` — contribution guide covering branching, commits, PR flow, and code style.
- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1.
- `SECURITY.md` — vulnerability disclosure policy.
- `.github/` issue + PR templates and CI workflow.
- Dashboard story-flow reorder: verdict → satellite + Windy → hourly breakdown → 10-day outlook → atmosphere → history → help.

## [0.1.0] - 2026-04-27

Initial public release.

### Added
- Python ingester pulling Open-Meteo forecast (60 min) and aviationweather.gov METAR/TAF (15 min).
- TimescaleDB schema with `forecast_hourly`, `metar_observations`, `taf_forecasts` hypertables and a `v_sunrise_window` aggregating view.
- Pure-Python flight-likelihood scoring with documented thresholds and unit tests.
- ERA5 historical backfill (~90 days) on first boot.
- Grafana OSS dashboard with anonymous viewer, six Cappadocia launch sites, and live LTAZ + LTAU airport observations.
- One-command Docker Compose stack (Postgres + ingester + Grafana + nginx).
- DigitalOcean deployment guide with HTTPS via Let's Encrypt.

[Unreleased]: https://github.com/allantumu/air-ballon/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/allantumu/air-ballon/releases/tag/v0.1.0
