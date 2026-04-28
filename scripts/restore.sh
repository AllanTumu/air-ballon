#!/usr/bin/env bash
# Restore the database from a gzipped pg_dump.
#
# Usage:
#   ./scripts/restore.sh ./backups/balloon-2026-04-28T03-00-00Z.sql.gz
#
# This is DESTRUCTIVE — it drops and recreates database objects. Make sure
# you really want to do this. There's a confirmation prompt unless FORCE=1.

set -euo pipefail

DUMP="${1:?Usage: $0 <path/to/dump.sql.gz>}"
COMPOSE_PROJECT_DIR="${COMPOSE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

if [[ ! -f "$DUMP" ]]; then
    echo "ERROR: dump file not found: $DUMP" >&2
    exit 1
fi

# Read just DB_USER and DB_NAME from .env (grep, not source — see backup.sh
# for the same reason).
if [[ -f "$COMPOSE_PROJECT_DIR/.env" ]]; then
    : "${DB_USER:=$(grep -E '^DB_USER=' "$COMPOSE_PROJECT_DIR/.env" | head -1 | cut -d= -f2-)}"
    : "${DB_NAME:=$(grep -E '^DB_NAME=' "$COMPOSE_PROJECT_DIR/.env" | head -1 | cut -d= -f2-)}"
fi

: "${DB_USER:?DB_USER not set}"
: "${DB_NAME:?DB_NAME not set}"

if [[ "${FORCE:-}" != "1" ]]; then
    echo "About to restore $DUMP into database '$DB_NAME'."
    echo "This will OVERWRITE all current data. Type 'yes' to continue:"
    read -r ANSWER
    [[ "$ANSWER" == "yes" ]] || { echo "Aborted."; exit 1; }
fi

cd "$COMPOSE_PROJECT_DIR"

echo "[restore] $(date -u -Iseconds) starting restore from $DUMP"
gunzip -c "$DUMP" | docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1
echo "[restore] $(date -u -Iseconds) done."

echo "[restore] You should restart the ingester so it picks up cleanly:"
echo "          docker compose restart ingester"
