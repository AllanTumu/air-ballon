# Deploying to DigitalOcean

This guide takes you from "blank account" to a publicly reachable dashboard at `https://your-domain` in about 30 minutes. The whole stack runs comfortably on the smallest standard droplet.

## 1. Provision the droplet

Recommended size: **Basic / Regular / 2 GB RAM / 1 vCPU / 50 GB SSD** (~$12/month). Memory matters more than CPU here — Postgres + Grafana + Python share well, but TimescaleDB benefits from headroom.

- Image: **Ubuntu 22.04 LTS x64**.
- Region: pick whichever is closest to your audience; for European traffic, `fra1` or `ams3` work well.
- Authentication: add your SSH public key. Don't enable password auth.
- Hostname: `cappadocia-balloons` (or whatever you like).

After it boots, you'll get an IP. Add an `A` record at your DNS provider:

```
Type: A
Host: cappadocia (or @ for a root domain)
Value: <droplet IP>
TTL: 300
```

Wait until `dig +short cappadocia.example.com` returns the droplet IP.

## 2. Harden the box (5 min)

SSH in as `root`:

```bash
ssh root@<IP>
```

Update and install Docker:

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl gnupg ufw fail2ban
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Make a non-root user to deploy as:

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo,docker deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```

Firewall — only SSH, HTTP, HTTPS:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
systemctl enable --now fail2ban
```

Disable root SSH and password auth:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

Log out and back in as `deploy`.

## 3. Deploy the stack (5 min)

```bash
cd ~
git clone https://github.com/AllanTumu/air-ballon.git
cd air-ballon
git checkout v0.1.0   # pin to a release tag — see docs/releases.md for the latest
cp .env.example .env
# Edit .env — change DB_PASSWORD, GRAFANA_ADMIN_PASSWORD, and set:
#   GRAFANA_ROOT_URL=https://your-domain
#   GRAFANA_DOMAIN=your-domain
nano .env
```

Bring it up:

```bash
docker compose up -d --build
docker compose logs -f ingester
```

You should see `forecast_ingested location=goreme rows=240` and similar log lines. After the first cycle (~1 minute), the dashboard is live on port 80.

Visit `http://your-domain` — you should see the dashboard, with anonymous access. Try clicking through. If you don't see any data yet, wait a minute for the first ingest cycle and refresh.

## 4. Add HTTPS (10 min)

Get certs with certbot via the webroot challenge:

```bash
DOMAIN=your-domain EMAIL=you@example.com make certbot
```

If that fails, the most common reason is DNS not yet pointing here. Confirm with `dig +short your-domain`.

Once the certs exist (`docker compose run --rm certbot certificates` will list them), edit `nginx/nginx.conf`:

1. Uncomment the entire HTTPS `server` block at the bottom.
2. Replace `DOMAIN_PLACEHOLDER` with your actual domain (3 occurrences).
3. In the HTTP `server` block, replace the `proxy_pass` block with `return 301 https://$host$request_uri;`.

Reload nginx:

```bash
docker compose restart nginx
```

Visit `https://your-domain` — should be green-padlock. Auto-renewal is handled by re-running `make certbot` in cron. Add to `deploy`'s crontab:

```bash
(crontab -l 2>/dev/null; echo "0 3 * * 1 cd ~/air-ballon && DOMAIN=your-domain EMAIL=you@example.com make certbot && docker compose exec nginx nginx -s reload") | crontab -
```

## 5. Operational basics

**View logs:**
```bash
docker compose logs -f ingester
docker compose logs -f grafana
```

**Backup the database** (DB only, ~10 MB after a few weeks):
```bash
docker compose exec db pg_dump -U $DB_USER $DB_NAME | gzip > backup-$(date +%F).sql.gz
```

**Update to a new release:**
```bash
git fetch --tags
git checkout v0.2.0       # pick the tag you want — see CHANGELOG.md
docker compose up -d --build
```

Pin production to a tag, not `main`. `main` is shippable but not release-verified.

**Roll back to the previous release:**
```bash
git checkout v0.1.0
docker compose up -d --build
```

Migrations are forward-only and additive, so rolling code back across a PATCH or MINOR is safe. Rolling across a MAJOR may need a database backup restore — see [docs/releases.md](docs/releases.md#rolling-back).

**Resource check:**
```bash
docker stats --no-stream
```

A 2GB droplet runs the stack at about 600 MB resident, with Postgres taking the most.

## 6. Make it your own

- Open `grafana/dashboards/cappadocia-flight-conditions.json` and change the title, links, attribution.
- Add a "Sponsor" row with a Buy-Me-a-Coffee link if you want to recoup hosting costs.
- Update the GitHub link in the dashboard JSON and `README.md` to your fork.
- Open issues for thresholds you'd like to tune. The community-validation aspect is the most valuable thing.

## Troubleshooting

**Dashboard loads but panels say "no data".** Check `docker compose logs ingester` for errors. Most common cause is a transient API outage; the next cycle will catch up. To force a refresh: `docker compose restart ingester`.

**`certbot` fails with "unauthorized".** Your domain isn't pointing at the droplet yet, or port 80 isn't reachable. `curl http://your-domain/.well-known/acme-challenge/test` from another machine — should return 404 from nginx, not connection refused.

**Grafana shows "Anonymous access disabled".** Double-check the `GF_AUTH_ANONYMOUS_*` env vars are set in your `.env` and `docker compose up -d` was re-run after editing.

**Forecast shows future data but nothing historical.** ERA5 backfill runs once on startup if `forecast_hourly` has < ~80% coverage of the lookback window. Force it: `docker compose restart ingester`.
