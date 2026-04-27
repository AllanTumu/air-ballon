# Release process

Releases are cut from `main` by a maintainer.

## Versioning

We follow [Semantic Versioning](https://semver.org/).

| Bump | When |
|---|---|
| MAJOR | Breaking changes to the database schema, the `.env` contract, or the dashboard export format. |
| MINOR | New dashboard panels, new data sources, new launch sites, new scheduled jobs. |
| PATCH | Bug fixes, threshold tuning, doc updates, dependency bumps. |

Pre-release suffixes (`-rc.1`, `-beta.1`) are allowed and trigger a GitHub pre-release rather than a stable one.

## Cutting a release

1. **Draft the changelog.** Move everything under `## [Unreleased]` in `CHANGELOG.md` into a new section:

   ```markdown
   ## [0.2.0] - 2026-05-12

   ### Added
   - …

   ### Fixed
   - …
   ```

   Keep the `## [Unreleased]` heading at the top, empty for now.

2. **Update the compare links** at the bottom of `CHANGELOG.md`:

   ```markdown
   [Unreleased]: https://github.com/AllanTumu/air-ballon/compare/v0.2.0...HEAD
   [0.2.0]: https://github.com/AllanTumu/air-ballon/compare/v0.1.0...v0.2.0
   [0.1.0]: https://github.com/AllanTumu/air-ballon/releases/tag/v0.1.0
   ```

3. **Open a release PR** titled `chore(release): v0.2.0`. Get it reviewed and merged. CI must be green.

4. **Tag the merge commit** on `main`:

   ```bash
   git checkout main
   git pull
   git tag -a v0.2.0 -m "v0.2.0"
   git push origin v0.2.0
   ```

   The `release.yml` workflow extracts the matching `## [0.2.0]` section from `CHANGELOG.md` and creates a GitHub Release.

5. **Verify the release** at `https://github.com/AllanTumu/air-ballon/releases`.

## Deploying a release

For self-hosters, see [DEPLOY.md](../DEPLOY.md). The short version on an existing droplet:

```bash
cd ~/air-ballon
git fetch --tags
git checkout v0.2.0
docker compose up -d --build
```

Pin to a tag in production rather than tracking `main`. `main` is shippable but unreleased changes haven't gone through release verification.

## Rolling back

If a release breaks production:

```bash
cd ~/air-ballon
git checkout v0.1.0          # the previous good tag
docker compose up -d --build
```

The database schema is forward-only (migrations are idempotent and additive). Rolling code back across a MAJOR version may require restoring a database backup — see the backup section of [DEPLOY.md](../DEPLOY.md).

## Hot-fix releases

For an urgent fix on top of the latest tag:

1. Branch from the tag: `git checkout -b hotfix/v0.2.1 v0.2.0`.
2. Cherry-pick or commit the fix.
3. Bump CHANGELOG.md to `## [0.2.1] - YYYY-MM-DD`.
4. Open a PR targeting `main`, merge, then tag `v0.2.1` on the merge commit.

We don't maintain long-lived release branches — every fix lands on `main` first, then is tagged.
