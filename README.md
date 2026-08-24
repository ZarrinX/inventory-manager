# inventory-mamager
Inventory control utilizing a UPC barcode scanner

Python/FastAPI app that reads a USB HID barcode scanner directly (keyboard-wedge
mode) and manages inventory in Postgres, with a live web dashboard.

## Setup

1. Start Postgres: `docker compose up -d`
2. Copy `.env.example` to `.env` and adjust as needed.
3. Find the scanner's device path and set `SCANNER_DEVICE_PATH` in `.env`:
   ```
   ls /dev/input/by-id/
   ```
4. The app needs read access to that device. Either run it as root, add your
   user to the `input` group (`sudo usermod -aG input $USER`, then re-login),
   or add a udev rule granting group `input` access to the device.
5. Install dependencies and run:
   ```
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
6. Open `http://<host>:8000/` — scan a barcode to look up or add an item.

Note: the scanner must be physically attached to the machine running the app
(e.g. the Raspberry Pi), since it reads the HID device directly.

---

## CI / CD — Jenkins

The `Jenkinsfile` at the repo root defines a Jenkins pipeline for automated
deployment to the Pi, matching the pattern used by `muthur-ui`.

| Stage | What it does |
|---|---|
| Checkout | Pulls latest code from SCM |
| Load Secrets | Symlinks `/opt/inventory-manager/.env` → `.env` so credentials are available at build time |
| Build & Deploy | Runs `docker compose up --build -d --remove-orphans` (builds the app image and starts it alongside Postgres) |
| Cleanup | Prunes dangling Docker images |

Table creation is handled automatically by the app on startup, so there's no
separate migrate/seed stage.

The pipeline requires a `.env` file at `/opt/inventory-manager/.env` on the
Jenkins agent (the Pi) containing `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, and `SCANNER_DEVICE_PATH`.

### Jenkins job setup

Create a Pipeline job pointing at this repo's `Jenkinsfile`, same as the
`muthur-ui` job:

1. Jenkins → New Item → Pipeline, name it `inventory-manager`.
2. Pipeline → Definition: "Pipeline script from SCM", SCM: Git,
   repo: `git@github.com:ZarrinX/inventory-mamager.git`, branch: `*/main`.
3. Add a build trigger (e.g. GitHub webhook or polling) matching the other jobs.


