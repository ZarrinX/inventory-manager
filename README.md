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

