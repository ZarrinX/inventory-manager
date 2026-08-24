# AGENTS.md — inventory-manager

Ammunition inventory control system built around a UPC/QR barcode scanner.
See [spec.md](spec.md) for the full product/technical spec and [todo.md](todo.md)
for the phased implementation checklist — check items off there as work lands.

## Architecture

- **Stack**: Python 3.12, FastAPI, SQLAlchemy, Postgres + Alembic migrations,
  Jinja2 + vanilla JS (no frontend framework/build step).
- **Domain model** (`app/models/`): a barcode/UPC (`AmmoPackageIdentifier`)
  resolves to an underlying `AmmoProduct`; multiple UPCs/package sizes can
  share one product (spec §24.1). Inventory only changes via immutable
  `InventoryTransaction` rows — a `ScanEvent` never mutates stock by itself
  (spec §3.1). `AmmoProduct.box_quantity`/`round_quantity` are denormalized
  running balances kept in sync whenever a transaction is created. Admin
  field configuration (`FieldDefinition`, `CustomFieldValue`,
  `DropdownOption`), `Location`, `InventoryViewPreference`, and `AuditEvent`
  round out the schema — see spec §11/§24 for the rationale behind each.
- **Scanner input**: the scanner ("Symcode Pro 1D 2D QR Wireless Barcode
  Scanner") acts as a USB HID keyboard. Instead of relying on window focus,
  `app/scanner.py` reads `/dev/input/by-id/usb-Scanner_Barcode_0215-event-kbd`
  directly via `evdev`, decodes keystrokes into full scan strings, and calls
  back into the app.
- **Data flow**: scan → UPC resolved against `AmmoPackageIdentifier` →
  `ScanEvent` recorded → broadcast to connected browsers over `/ws/scans`
  (`app/broadcast.py`) → dashboard updates live (`app/static/js/app.js`). The
  full unknown/known-UPC modal workflow, scan queue, and debounce from the
  spec are not yet implemented (see todo.md Phase 3/6).
- **Hardware**: the scanner is physically attached to the Raspberry Pi
  (`zrice@10.64.32.100`, hostname `Pi5`), so the app must run there — it
  won't see scans if run elsewhere.

## Key files

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app, lifespan startup (starts scanner thread), routes |
| `app/scanner.py` | Background thread reading the HID device via evdev |
| `app/models/` | SQLAlchemy models split by concern (ammo, transactions, scan, fields, location, preferences, audit) |
| `app/services/` | Business logic shared by routers and the scanner handler (identifier resolution, transaction creation, scan recording) |
| `app/routers/ammo.py` | Thin REST API: list/create products, lookup by UPC, create transactions — delegates to `app/services/` |
| `app/broadcast.py` | WebSocket connection manager for live scan push |
| `alembic/` | Migrations — schema is Alembic-managed, no `create_all()` in production |
| `docker-compose.yml` | `app` + `postgres` services for local dev and deployment |
| `Jenkinsfile` | CI/CD pipeline (mirrors `muthur-ui`'s pattern), includes an `alembic upgrade head` stage |

## Local development

```
docker compose up -d postgres
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

The scanner device won't exist on a dev machine — `ScannerReader` catches
`OSError` and retries every 5s, so the rest of the app still works locally.

### Generating a new migration

Postgres isn't published to the host (see gotchas below), so run Alembic
inside a one-off container on the compose network, bind-mounting `alembic/`
so the generated file lands on the host instead of being lost with the
container:

```
docker compose up -d postgres
docker compose build app
docker compose run --rm --no-deps --entrypoint "" -v "$(pwd)/alembic:/app/alembic" app \
  alembic revision --autogenerate -m "description"
# fix ownership without needing host sudo — chown from inside a root container instead:
docker compose run --rm --no-deps --entrypoint "" -v "$(pwd)/alembic:/app/alembic" app \
  chown -R $(id -u):$(id -g) /app/alembic/versions
```

## Deployment (Jenkins CI/CD on the Pi)

- Jenkins runs directly on the Pi (`http://10.64.32.100:8080`), same instance
  used by `muthur-ui`. Jenkins MCP tools are available for build status/logs.
- Job: `inventory-manager`, polls `main` every 2 minutes, credential
  `github-pat-auth`.
- Pipeline: checkout → symlink `/opt/inventory-manager/.env` → `.env` →
  `docker compose up --build -d --remove-orphans` → `alembic upgrade head` →
  prune images.
- `/opt/inventory-manager/.env` on the Pi holds `POSTGRES_DB`,
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `SCANNER_DEVICE_PATH`.
- Schema changes are Alembic-managed (`alembic/versions/`) — there is no
  `Base.metadata.create_all()` fallback anymore.

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
- **Alembic + SQLAlchemy Enum columns**: `sa.Enum(SomePyEnum)` stores the
  enum member's **name** (e.g. `"TEXT"`), not its `.value` (e.g. `"text"|"`),
  unless `values_callable` is set. Data migrations that insert enum values
  must use the member name to match what autogenerate put in the DDL.
- **Docker bind mounts + root-owned files**: running one-off `docker compose
  run` commands (e.g. `alembic revision --autogenerate`) with a bind mount
  writes files as root on the host, since the container runs as root. Fix
  ownership from *inside* another root container
  (`chown -R $(id -u):$(id -g) ...`) instead of host `sudo`, to avoid
  interactive password prompts.

## Conventions

- Do not `git push` automatically — commit locally and let the user decide
  when to push.
- Repo was originally named `inventory-mamager` (typo) and later renamed to
  `inventory-manager` on GitHub; the Jenkins job and `/opt` secrets path use
  the corrected name.
