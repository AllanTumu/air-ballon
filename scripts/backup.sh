#!/usr/bin/env bash
# Database backup script for the balloon dashboard.
#
# Dumps the Postgres/TimescaleDB database, gzips it, and either:
#   - Stores locally under ./backups/ (default), OR
#   - Uploads to a remote storage backend via rclone (set BACKUP_REMOTE).
#
# Designed to be safe under cron — no interactive prompts, sets clean
# error handling, exits non-zero on any failure so cron can email you.
#
# Usage:
#   ./scripts/backup.sh                          # local backup
#   BACKUP_REMOTE=r2:balloon-backups ./scripts/backup.sh   # remote
#   RETAIN_DAYS=14 ./scripts/backup.sh           # tweak local retention
#
# Dependencies on the host:
#   - docker (for `docker compose exec db pg_dump`)
#   - gzip
#   - rclone (only if using BACKUP_REMOTE)

set -euo pipefail

# --- Config ------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
RETAIN_DAYS="${RETAIN_DAYS:-30}"
RETAIN_REMOTE_DAYS="${RETAIN_REMOTE_DAYS:-90}"
COMPOSE_PROJECT_DIR="${COMPOSE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

# Load .env for DB_USER / DB_NAME if not already in the environment.
if [[ -z "${DB_USER:-}" || -z "${DB_NAME:-}" ]]; then
    if [[ -f "$COMPOSE_PROJECT_DIR/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        . "$COMPOSE_PROJECT_DIR/.env"
        set +a
    fi
fi

: "${DB_USER:?DB_USER not set (in env or .env)}"
: "${DB_NAME:?DB_NAME not set (in env or .env)}"

# --- Output paths ------------------------------------------------------------
TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/balloon-${TIMESTAMP}.sql.gz"

echo "[backup] $(date -u -Iseconds) starting backup -> $OUT"

# --- Dump --------------------------------------------------------------------
# `pg_dump --no-owner --no-privileges` makes the dump portable to any host;
# `--clean --if-exists` lets it restore over an existing DB cleanly.
cd "$COMPOSE_PROJECT_DIR"
docker compose exec -T db \
    pg_dump \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-owner \
        --no-privileges \
        --clean --if-exists \
    | gzip --best > "$OUT"

SIZE_HUMAN="$(du -h "$OUT" | awk '{print $1}')"
echo "[backup] dump complete: $SIZE_HUMAN"

# --- Upload (if remote configured) -------------------------------------------
if [[ -n "$BACKUP_REMOTE" ]]; then
    if ! command -v rclone >/dev/null 2>&1; then
        echo "[backup] ERROR: BACKUP_REMOTE set but rclone not installed." >&2
        exit 2
    fi
    echo "[backup] uploading to $BACKUP_REMOTE"
    rclone copy "$OUT" "$BACKUP_REMOTE" --progress
    echo "[backup] upload complete"

    # Prune remote — keep daily for RETAIN_REMOTE_DAYS
    rclone delete "$BACKUP_REMOTE" \
        --min-age "${RETAIN_REMOTE_DAYS}d" \
        --include 'balloon-*.sql.gz' || true
fi

# --- Prune local -------------------------------------------------------------
find "$BACKUP_DIR" -name 'balloon-*.sql.gz' -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true

echo "[backup] $(date -u -Iseconds) done. Local backups kept: ${RETAIN_DAYS}d. Remote: ${RETAIN_REMOTE_DAYS}d."
