# Contributing

Thanks for considering a contribution. This project exists because someone (the author) flew a long way for a Cappadocia balloon ride and got cancelled, and most travellers and tour guides don't have the meteorology background to read the forecast themselves. Anything that makes the dashboard more accurate, more accessible, or more useful is welcome.

## Ways to help

You don't have to write code to make this better. Things we especially value:

- **Calibration data.** If you live in Cappadocia, work for an operator, or have flown there, tell us about a morning where our verdict didn't match what actually happened. Open an issue with the date and what you observed. This is the highest-value contribution.
- **Translations.** The dashboard is in English. Turkish first, then any tourist language, would help local users.
- **New data sources.** EUMETSAT satellite fog detection, Sentinel Hub imagery, MGM scraping if you can do it nicely — all welcome.
- **Threshold tuning.** Our scoring thresholds were set from desk research. If you have ground-truth on what wind speed actually grounds operators in Cappadocia, we'd love to refine them.
- **Bug reports.** Reproducible bug reports are gold. Tell us what you did, what you expected, what happened, and your environment.
- **Documentation.** If something in the README or DEPLOY guide didn't work for you, please open a PR fixing it.
- **Code.** Of course.

Before you start substantial work, please open an issue to discuss it. This avoids the disappointment of an unmergeable PR.

## Quick start for development

```bash
git clone https://github.com/AllanTumu/air-ballon.git
cd air-ballon
cp .env.example .env
# Edit .env — change DB_PASSWORD and GRAFANA_ADMIN_PASSWORD at minimum.
docker compose up -d --build
docker compose logs -f ingester
```

Run unit tests:

```bash
make test
```

Open the dashboard at <http://localhost:3030> (or whichever port you set as `GRAFANA_HOST_PORT`).

For more on system design, read [ARCHITECTURE.md](ARCHITECTURE.md).

## Branching & commits

We use **trunk-based development**. `main` is always shippable.

- Branch from `main`, name your branch `<type>/<short-slug>` — e.g. `feat/satellite-fog`, `fix/timezone-bug`, `docs/contributing`.
- Keep PRs small. One logical change per PR. If you find yourself touching unrelated files, split into multiple PRs.
- Write **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`. Use the body to explain *why*, not *what*.

Example commit messages:

```
feat(scoring): add inversion penalty when boundary layer < 50m at sunrise

Cappadocia valleys frequently form shallow inversions overnight. Until now
we tracked boundary layer height in the dashboard but didn't penalise the
score. This deducts 6 points when BLH < 50m, matching observed cancellation
patterns from Aug 2024.

Closes #42
```

```
fix(grafana): inline location_id subquery instead of using template var

The hidden $location_id template variable wasn't resolving reliably in some
Grafana versions, leaving panels blank. Inline (SELECT id FROM locations
WHERE slug = '$launch_site') in every query — slightly more verbose but
deterministic.
```

## Pull request flow

1. Open a draft PR early so others can see what you're working on.
2. Make sure CI is green — `make test` locally first.
3. Update [CHANGELOG.md](CHANGELOG.md) under `## [Unreleased]` with a one-liner. Format: `- Added: ... (#PR)` or `- Fixed: ...`.
4. If you changed thresholds, run the unit tests and update [docs/data-sources.md](docs/data-sources.md).
5. Mark the PR ready for review.
6. A maintainer will review and merge with **squash merge**. The squashed commit message is your PR title — make it descriptive.

## Code style

**Python**:
- Format with `ruff format` (line length 100).
- Lint with `ruff check`.
- Type hints required on public functions; private helpers can skip them if obvious.
- Prefer dataclasses over dicts for non-DB-row data.
- Log with `structlog`, not `print`.

**SQL**:
- Migrations are immutable once merged. Add new ones with the next number (`003_…sql`, `004_…sql`).
- All migrations must be idempotent. Use `IF NOT EXISTS`, `ON CONFLICT`, `CREATE OR REPLACE`.
- TimescaleDB-specific features must use `if_not_exists => TRUE` so re-runs don't error.

**Grafana**:
- Edit dashboards in the Grafana UI as admin, then export and commit the JSON.
- Pin every panel's data source UID to `Balloon-DB`.
- Don't introduce hidden template variables that depend on each other; inline subqueries are more reliable.
- Run dashboard JSON through a linter (`jq -e .` minimum) before committing.

**Docker / config**:
- Never commit secrets. `.env` is gitignored; only `.env.example` is checked in.
- Volumes for stateful services (`db_data`, `grafana_data`) — the rest is rebuilt from the image.

## Reporting a bug

Open an issue using the **Bug report** template. Include:

- What you tried to do
- What you expected
- What happened
- Reproducible steps from a clean clone
- Environment: OS, Docker version, Grafana version, browser if relevant
- Logs (`docker compose logs ingester | tail -100`)

## Suggesting a data source

Open an issue using the **New data source** template. Include:

- Source name and URL
- Whether it's free, requires registration, or has an API key
- Rate limits
- License of the data (CC-BY, public domain, proprietary?)
- What value it adds to the dashboard

We'll bias toward sources that are free, public, well-documented, and stable.

## Calibration / threshold tuning

Open an issue using the **Threshold calibration** template. Include:

- The date and morning in question
- What our dashboard would have shown (verdict + score)
- What actually happened (flew / cancelled / partial slots)
- Source for the actual outcome (operator post, your own observation, news report)

Multiple data points beat a single one. We'll batch these and run a calibration pass periodically.

## Code of conduct

Participation requires reading and following [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Short version: be kind, assume good faith, no harassment.

## Licensing

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE) of this project.

## Maintainers

If you'd like to become a maintainer (review PRs, triage issues), the path is: contribute substantively for 3+ months, then ask. We trend toward growing the maintainer pool, not gatekeeping.
