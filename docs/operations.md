# Operations: keeping the dashboard healthy

This is the hands-on guide for the production server. If you've followed [DEPLOY.md](../DEPLOY.md), the stack is already running — this doc is what you do *after* that to keep it running well.

## Daily life

Most of the time you don't need to do anything. The ingester runs every 60 minutes (forecast) and every 15 minutes (METAR/TAF). TimescaleDB's retention and compression policies run in the background.

### Checking that it's healthy

```bash
docker compose ps               # All four containers should be Up / healthy.
docker compose logs --tail=50 ingester
make db-size                    # Per-table storage.
```

### Updating to a new release

```bash
cd ~/air-ballon
git pull
docker compose up -d --build
make migrate                    # only if migrations 003+ aren't applied yet
```

`docker compose up -d --build` rebuilds the ingester image; the database, Grafana, and nginx containers stay running unless their image tags or env vars changed.

## Database maintenance

### Storage growth and retention

The schema in `db/migrations/001_init.sql` already defines retention policies that automatically drop old data:

| Table | Retention |
|---|---|
| `forecast_hourly` | 395 days |
| `metar_observations` | 180 days |
| `taf_forecasts` | 90 days |

Inspect what's running:

```sql
SELECT * FROM timescaledb_information.jobs ORDER BY proc_name;
```

### Compression

Migration `003_compression.sql` enables columnar compression on chunks older than the thresholds below. Forecast data compresses extremely well (10-20× smaller).

| Table | Compress after |
|---|---|
| `forecast_hourly` | 14 days |
| `metar_observations` | 30 days |
| `taf_forecasts` | 14 days |

Apply on the live DB:

```bash
make migrate
```

Inspect compression effectiveness once chunks have aged into compression:

```bash
make db-compression-stats
```

### Continuous aggregate

Migration `004_continuous_aggregate.sql` converts the `v_sunrise_window` view into a TimescaleDB continuous aggregate. It pre-computes the per-day rollups the dashboard needs and refreshes incrementally as new forecasts arrive — so the daily-strip and historical panels stay fast as the table grows.

The dashboard SQL is unchanged because the public-facing view name (`v_sunrise_window`) and column shape are preserved.

## Backups

The DB is the only stateful piece worth backing up. Grafana state is in a Docker volume but easily rebuilt; the dashboard JSON lives in git.

### What we back up

A nightly `pg_dump` of the whole `balloon` database:
- All locations
- All forecasts (compressed, decompressed transparently into the dump)
- All METAR / TAF observations
- The continuous aggregate metadata

A typical compressed dump is a few hundred KB to a few MB depending on how much history has accrued. Cheap to keep.

### Local-only backups (default)

```bash
make backup
```

This calls `scripts/backup.sh`, which writes a gzipped dump to `./backups/`. Local backups are kept for 30 days by default (`RETAIN_DAYS` env var to change).

Add to crontab for automation:

```bash
crontab -e
# Daily at 02:00 UTC
0 2 * * * cd /home/deploy/air-ballon && /usr/bin/make backup >> /var/log/balloon-backup.log 2>&1
```

### Remote backups (recommended for production)

A local-only backup doesn't survive disk loss. Push to a remote with rclone.

#### Option A: Cloudflare R2 (free tier covers this project)

R2 gives 10 GB free storage and free egress. A few years of nightly backups easily fit.

1. Create an R2 bucket: `wrangler r2 bucket create balloon-backups` (or via the Cloudflare dashboard).
2. Generate an R2 API token with read/write to that bucket.
3. Install rclone on the server and configure it:

   ```bash
   sudo apt install rclone -y
   rclone config
   # Choose: n (new remote)
   # Name: r2
   # Storage: s3
   # Provider: Cloudflare
   # AWS access key ID:    <your R2 access key>
   # AWS secret access key: <your R2 secret>
   # Region: auto
   # Endpoint: https://<your-account-id>.r2.cloudflarestorage.com
   ```

4. Test:

   ```bash
   rclone lsd r2:                    # should list your bucket
   rclone copy /etc/hostname r2:balloon-backups   # smoke test
   ```

5. Run a backup that uploads:

   ```bash
   BACKUP_REMOTE=r2:balloon-backups make backup
   ```

6. Add to crontab:

   ```cron
   0 2 * * * cd /home/deploy/air-ballon && BACKUP_REMOTE=r2:balloon-backups /usr/bin/make backup >> /var/log/balloon-backup.log 2>&1
   ```

Remote backups are pruned to 90 days by default (`RETAIN_REMOTE_DAYS`).

#### Option B: Hetzner Storage Box

Hetzner sells Storage Boxes (€3.20/mo for 1 TB) that mount via SFTP/SMB. Same flow as R2 but with the Storage Box as the rclone remote.

### Restoring from backup

```bash
# Pick a dump file
ls backups/

# Or fetch one from R2
rclone copy r2:balloon-backups/balloon-2026-04-28T02-00-00Z.sql.gz ./backups/

# Restore (will OVERWRITE the current DB):
make restore DUMP=./backups/balloon-2026-04-28T02-00-00Z.sql.gz

# Restart the ingester so it reconnects cleanly:
docker compose restart ingester
```

The restore script asks for confirmation. Set `FORCE=1` to skip the prompt for scripted use.

## Common operations

### Force an ingest cycle now

```bash
docker compose restart ingester
```

The ingester runs forecast + METAR + backfill once on startup, then enters its scheduler.

### Add a new launch site

Edit `db/migrations/002_seed_locations.sql` to add a row, then either:

```bash
# If the migration has already run on this DB, run the INSERT manually:
docker compose exec db psql -U "$DB_USER" -d "$DB_NAME" -c "
INSERT INTO locations (slug, name, kind, latitude, longitude, elevation_m, notes)
VALUES ('bagan', 'Bagan', 'launch_site', 21.1717, 94.8585, 70, 'Myanmar — sunrise pagoda flights')
ON CONFLICT (slug) DO NOTHING;"
```

The ingester picks up the new row on its next forecast cycle (within an hour).

### View what the auto-renewal cron will do

```bash
crontab -l
```

### Tail just the scoring decisions in real time

```bash
docker compose logs -f ingester | grep flight_verdict
```

### Pause backups temporarily

```bash
crontab -l | grep -v balloon-backup | crontab -
```

…and reverse with `crontab -e`.

## When something breaks

### Dashboard panels show "No data"

```bash
docker compose ps                     # are all services up?
docker compose logs --tail=50 ingester
docker compose logs --tail=50 db
```

The ingester logs print `forecast_ingested location=goreme rows=240` on each cycle. If you're not seeing those, check Open-Meteo from the server: `curl -sI https://api.open-meteo.com/`.

### nginx in a crash loop after a config change

```bash
docker compose logs --tail=30 nginx
```

The error is almost always a missing cert file (HTTPS server block referencing a path that doesn't exist) or a syntax error. Restore the previous nginx.conf and restart:

```bash
git checkout nginx/nginx.conf
docker compose restart nginx
```

### Disk filling up

```bash
df -h /
docker system df
make db-size
make db-compression-stats
```

If TimescaleDB hypertables are large, `make db-compression-stats` will show whether compression is keeping up. If not, check `SELECT * FROM timescaledb_information.jobs` for paused or failing compression jobs.

### Need to roll back

The repo is tag-pinnable (see DEPLOY.md). For a code-only roll-back:

```bash
git checkout v0.1.0
docker compose up -d --build
```

For a data roll-back, restore from a backup:

```bash
make restore DUMP=./backups/balloon-<good-date>.sql.gz
```

## Cost summary (current setup)

| Item | Monthly | Annual |
|---|---|---|
| Hetzner CX23 (Helsinki) | €4.83 | €58 |
| IPv4 address | €0.61 | €7 |
| Domain (`shallweflytomorrow.com`) | — | ~$10 |
| Cloudflare R2 backups | €0 (free tier) | — |
| **Total** | **€5.43** | **~€75** |

If you outgrow the CX23 (more than ~30 launch sites or want to add satellite imagery), step up to **CPX31** (4 vCPU AMD / 8 GB RAM / 160 GB / €13.10/mo). The schema and ingester scale linearly with location count.
