# Dashboard enhancement pack

This page documents the optional features in the dashboard that go beyond the core forecast logic. Everything here is free to run, with no AI / LLM dependencies and no third-party API keys required (with one exception: webcam URL is yours to swap).

## In the dashboard JSON

These are pure Grafana panels. They light up automatically once the dashboard is reloaded.

### Pressure trend (panel id 60)

Shows the change in mean sea-level pressure over the last 3 hours vs. the 3 hours before that. Falling pressure (negative delta) often precedes worsening weather; rising pressure suggests settling conditions. Aviation people read this instinctively; for non-experts the arrow + colour conveys it at a glance.

Mappings:

- ↘ Falling fast (≤ −1.5 hPa)
- ↘ Falling (−1.5 to −0.3)
- → Steady (−0.3 to +0.3)
- ↗ Rising (+0.3 to +1.5)
- ↗ Rising fast (≥ +1.5)

### Days since last NO-CHANCE morning (panel id 61)

Counter that resets to 0 each time we predicted a NO CHANCE morning. A streak of 7+ days is a viral screenshot.

### Yesterday's verdict vs. reality (panel id 62)

Compares yesterday's predicted verdict against the live METAR observations from LTAZ during the launch window. Outcome buckets: matched, marginal, mismatch, no-data. Builds trust by showing we check ourselves automatically.

### Sponsor / coffee panel (panel id 64)

A small footer card with a Buy Me a Coffee button and a "Star on GitHub" link. **Replace `buymeacoffee.com/yourname` with your actual handle** before going live. Set your username in the dashboard JSON; the panel is intentionally low-key — non-aggressive.

## RainViewer rain radar overlay

Added as an XYZ tile layer on the existing satellite Geomap (panel id 50). RainViewer's free public API needs no key, returns ~2 hours of recent radar history. Layer ordering: rain sits below the launch-site markers so dots stay visible.

If you want to remove it later, drop the layer from the geomap's `options.layers` array.

## PWA — add to home screen

Three static files in `static/`:

- `manifest.webmanifest` — app metadata, icon paths, start URL
- `sw.js` — minimal service worker (network-first, no aggressive caching — the dashboard's value is freshness)
- `robots.txt` — search engine indexing hints

Nginx serves these at the site root (see `nginx/nginx.conf`'s `location /manifest.webmanifest` etc. blocks). Once deployed, mobile visitors see "Add to Home Screen" in their browser menu and the dashboard launches full-screen with the balloon icon.

**To make the install prompt actually work**, you need icon images. Place them at:

```
static/icons/icon-192.png
static/icons/icon-512.png
static/icons/icon-512-maskable.png
```

Generate them once with any tool (Figma, an online PWA icon generator, or `convert input.png -resize 192x192 output.png`). The icons are not in git — they're branded artwork you pick.

## iCal feed

Visitors subscribe to `https://shallweflytomorrow.com/calendar.ics` from Apple Calendar / Google Calendar / Outlook and see the next 10 days of HIGH CHANCE / MAYBE / NO CHANCE mornings appear as all-day events.

### Wiring it up

1. The script `scripts/generate_ical.py` reads `v_sunrise_window` from the running database via `docker compose exec`, formats an iCal feed, and writes it to a static path.
2. Add it to crontab so it refreshes every 15 minutes:

   ```cron
   */15 * * * * cd /home/deploy/air-ballon && /usr/bin/python3 scripts/generate_ical.py /home/deploy/air-ballon/static/calendar.ics >> /tmp/balloon-ical.log 2>&1
   ```

3. Make sure nginx serves `/calendar.ics` from `static/`. The block (already in the recommended nginx.conf below) is:

   ```nginx
   location = /calendar.ics {
       alias /var/www/static/calendar.ics;
       add_header Content-Type "text/calendar; charset=utf-8";
       add_header Cache-Control "public, max-age=600";
   }
   ```

4. Mount the static directory into the nginx container (already in `docker-compose.yml` if you're on the latest version):

   ```yaml
   nginx:
     volumes:
       - ./static:/var/www/static:ro
   ```

### Testing

```bash
# Generate locally:
python3 scripts/generate_ical.py /tmp/calendar.ics
head -30 /tmp/calendar.ics

# Subscribe (Apple Calendar): File -> New Calendar Subscription -> paste URL.
# Subscribe (Google Calendar): "Other calendars" -> "From URL".
```

## Future, non-AI extensions

Documented for future work, not built yet:

- **Public JSON API** at `/api/v1/score?lat=&lon=&date=` — needs a small FastAPI service alongside the ingester.
- **Status badge** at `/badge.svg` for embedding in blogs/READMEs.
- **Auto social cards** — cron job that renders a 1080×1080 PNG and posts to Bluesky/Mastodon (free APIs).
- **Calibration submission form** — needs a small form-handling backend to write to a `flight_outcomes` table.
- **Sunrise/sunset times** — small ingester change to also store Open-Meteo's `daily.sunrise/sunset` fields in a new `daily_astro` table.

Each is a self-contained afternoon's work. Tackle them in whatever order matches the audience you grow.
