# AGENTS.md — inventory-manager

Inventory control system built around a UPC/QR barcode scanner. Reads scans
directly from the scanner's USB HID device and manages stock levels in
Postgres, with a live web dashboard.

## Architecture

- **Stack**: Python 3.12, FastAPI, SQLAlchemy, Postgres, Jinja2 + vanilla JS
  (no frontend framework/build step).
- **Scanner input**: the scanner ("Symcode Pro 1D 2D QR Wireless Barcode
  Scanner") acts as a USB HID keyboard. Instead of relying on window focus,
  `app/scanner.py` reads `/dev/input/by-id/usb-Scanner_Barcode_0215-event-kbd`
  directly via `evdev`, decodes keystrokes into full scan strings, and calls
  back into the app.
- **Data flow**: scan → looked up/logged in Postgres (`Item`, `ScanEvent` in
  `app/models.py`) → broadcast to connected browsers over `/ws/scans`
  (`app/broadcast.py`) → dashboard updates live (`app/static/js/app.js`).
- **Hardware**: the scanner is physically attached to the Raspberry Pi
  (`zrice@10.64.32.100`, hostname `Pi5`), so the app must run there — it
  won't see scans if run elsewhere.

## Key files

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app, lifespan startup (creates DB tables, starts scanner thread), routes |
| `app/scanner.py` | Background thread reading the HID device via evdev |
| `app/models.py` | SQLAlchemy models: `Item`, `ScanEvent` |
| `app/routers/items.py` | REST API for item CRUD + quantity adjustment |
| `app/broadcast.py` | WebSocket connection manager for live scan push |
| `docker-compose.yml` | `app` + `postgres` services for local dev and deployment |
| `Jenkinsfile` | CI/CD pipeline (mirrors `muthur-ui`'s pattern) |

## Local development

```
docker compose up -d postgres
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The scanner device won't exist on a dev machine — `ScannerReader` catches
`OSError` and retries every 5s, so the rest of the app still works locally.

## Deployment (Jenkins CI/CD on the Pi)

- Jenkins runs directly on the Pi (`http://10.64.32.100:8080`), same instance
  used by `muthur-ui`. Jenkins MCP tools are available for build status/logs.
- Job: `inventory-manager`, polls `main` every 2 minutes, credential
  `github-pat-auth`.
- Pipeline: checkout → symlink `/opt/inventory-manager/.env` → `.env` →
  `docker compose up --build -d --remove-orphans` → prune images.
- `/opt/inventory-manager/.env` on the Pi holds `POSTGRES_DB`,
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `SCANNER_DEVICE_PATH`.
- Table creation is automatic on app startup (`Base.metadata.create_all`) —
  no separate migrate/seed stage needed.

### Gotchas learned the hard way

- **Port conflicts**: `muthur-ui` already publishes Postgres on host port
  5432 on the same Pi. Our `postgres` service must **not** publish 5432 to
  the host — the app reaches it over the internal compose network only.
- **evdev build deps**: compiling evdev's C extension needs
  `build-essential` + `linux-libc-dev` in the Docker image (plain
  `python:3.12-slim` is missing both gcc and libc headers).
- **Jenkins CLI/REST reload is blocked**: `jenkins-cli.jar` and the reload
  REST endpoint fail with a reverse-proxy origin check on this instance. New
  jobs created by writing `config.xml` directly to
  `/var/lib/jenkins/jobs/<name>/` require a full `sudo systemctl restart
  jenkins` to be discovered — there's no live-reload workaround found so far.
- **Git credential scope**: the Jenkins Git credential can be scoped to
  specific repos (GitHub App/fine-grained PAT). A 403 "Write access to
  repository not granted" on a plain `git fetch` means the credential needs
  the new repo added to its access list, not a code fix.

## Conventions

- Do not `git push` automatically — commit locally and let the user decide
  when to push.
- Repo was originally named `inventory-mamager` (typo) and later renamed to
  `inventory-manager` on GitHub; the Jenkins job and `/opt` secrets path use
  the corrected name.
