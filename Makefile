.PHONY: up down logs ingest test fresh certbot dashboard-export

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
