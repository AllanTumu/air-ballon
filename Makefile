.PHONY: up down logs ingest test fresh certbot dashboard-export migrate backup restore db-size db-compression-stats

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

# One-shot ingest run (does forecast + METAR + historical backfill, then exits).
ingest:
	docker compose run --rm ingester python -c "from main import job_forecast, job_aviation, maybe_backfill, settings; from config import Settings; import db; settings = Settings.from_env(); db.init_pool(settings.db_dsn); job_forecast(); job_aviation(); maybe_backfill()"

test:
	cd ingester && python3 -m unittest discover -v tests

# Wipe everything (DB + Grafana state). DESTRUCTIVE.
fresh:
	docker compose down -v
	docker compose up -d --build

# Issue certs — only run once, with DOMAIN env set.
certbot:
	@if [ -z "$$DOMAIN" ] || [ -z "$$EMAIL" ]; then echo "Set DOMAIN=your.domain EMAIL=you@example.com"; exit 1; fi
	docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d $$DOMAIN --email $$EMAIL --agree-tos --no-eff-email

dashboard-export:
	@PORT=$${GRAFANA_HOST_PORT:-3030}; \
	curl -s -u $$GRAFANA_ADMIN_USER:$$GRAFANA_ADMIN_PASSWORD http://localhost:$$PORT/api/dashboards/uid/cappadocia-balloons | jq .dashboard > grafana/dashboards/cappadocia-flight-conditions.json
	@echo "Exported. Don't forget to clean the 'id' and 'version' fields before committing."

# --- Database maintenance --------------------------------------------------

# Apply any new migrations against the running DB (for migrations beyond 002,
# which run only on first DB init via docker-entrypoint-initdb.d). Idempotent
# — every migration uses CREATE ... IF NOT EXISTS / ON CONFLICT / etc.
migrate:
	@for f in db/migrations/*.sql; do \
		echo ">>> Applying $$f"; \
		docker compose exec -T db psql -U $$(grep ^DB_USER .env | cut -d= -f2) -d $$(grep ^DB_NAME .env | cut -d= -f2) -v ON_ERROR_STOP=1 < $$f; \
	done

# Take a backup. Set BACKUP_REMOTE=r2:bucket/path to also push to a remote
# rclone target (run `rclone config` once first to set up the remote).
backup:
	./scripts/backup.sh

# Restore from a dump file: make restore DUMP=./backups/balloon-XYZ.sql.gz
restore:
	@test -n "$(DUMP)" || (echo "Usage: make restore DUMP=path/to/dump.sql.gz" && exit 1)
	./scripts/restore.sh $(DUMP)

# Quick size summary of the database.
db-size:
	@docker compose exec -T db psql -U $$(grep ^DB_USER .env | cut -d= -f2) -d $$(grep ^DB_NAME .env | cut -d= -f2) -c "\
		SELECT \
			schemaname || '.' || relname AS table, \
			pg_size_pretty(pg_total_relation_size(C.oid)) AS total_size \
		FROM pg_class C LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace) \
		WHERE nspname NOT IN ('pg_catalog','information_schema','_timescaledb_internal','_timescaledb_catalog','_timescaledb_config','_timescaledb_cache') \
		  AND C.relkind = 'r' \
		ORDER BY pg_total_relation_size(C.oid) DESC;"

# Compression effectiveness on the hypertables.
db-compression-stats:
	@docker compose exec -T db psql -U $$(grep ^DB_USER .env | cut -d= -f2) -d $$(grep ^DB_NAME .env | cut -d= -f2) -c "\
		SELECT hypertable_name, \
			pg_size_pretty(before_compression_total_bytes) AS before, \
			pg_size_pretty(after_compression_total_bytes)  AS after, \
			ROUND(100.0 * after_compression_total_bytes / NULLIF(before_compression_total_bytes,0), 1) AS pct_kept \
		FROM hypertable_compression_stats('forecast_hourly') \
		UNION ALL \
		SELECT hypertable_name, \
			pg_size_pretty(before_compression_total_bytes), \
			pg_size_pretty(after_compression_total_bytes), \
			ROUND(100.0 * after_compression_total_bytes / NULLIF(before_compression_total_bytes,0), 1) \
		FROM hypertable_compression_stats('metar_observations') \
		UNION ALL \
		SELECT hypertable_name, \
			pg_size_pretty(before_compression_total_bytes), \
			pg_size_pretty(after_compression_total_bytes), \
			ROUND(100.0 * after_compression_total_bytes / NULLIF(before_compression_total_bytes,0), 1) \
		FROM hypertable_compression_stats('taf_forecasts');"
