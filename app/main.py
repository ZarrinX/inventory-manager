import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.broadcast import manager
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import AmmoPackageIdentifier, AmmoProduct, ScanEvent
from app.routers import ammo
from app.scanner import ScannerReader

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

_scanner: ScannerReader | None = None


def _handle_scan(payload: str, loop: asyncio.AbstractEventLoop) -> None:
    """Runs on the scanner's background thread: records the scan event and
    schedules a broadcast on the app's event loop. Never mutates inventory
    itself (spec §3.1) — that only happens via a confirmed transaction."""
    db: Session = SessionLocal()
    try:
        identifier = db.scalar(
            select(AmmoPackageIdentifier).where(
                AmmoPackageIdentifier.upc == payload, AmmoPackageIdentifier.active.is_(True)
            )
        )
        product = None
        if identifier:
            product = db.scalar(
                select(AmmoProduct)
                .options(selectinload(AmmoProduct.identifiers))
                .where(AmmoProduct.id == identifier.ammo_product_id)
            )

        event = ScanEvent(payload=payload, ammo_product_id=product.id if product else None)
        db.add(event)
        db.commit()

        result = {
            "upc": payload,
            "scanned_at": event.scanned_at.isoformat(),
            "product": {
                "id": product.id,
                "manufacturer": product.manufacturer,
                "product_line": product.product_line,
                "cartridge": product.cartridge,
                "box_quantity": product.box_quantity,
                "round_quantity": product.round_quantity,
            }
            if product
            else None,
        }
    finally:
        db.close()

    asyncio.run_coroutine_threadsafe(manager.broadcast(result), loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scanner
    # Schema is managed by Alembic migrations (see alembic/), not created here.

    loop = asyncio.get_event_loop()
    try:
        _scanner = ScannerReader(
            settings.scanner_device_path, lambda payload: _handle_scan(payload, loop)
        )
        _scanner.start()
        logger.info("Scanner reader started on %s", settings.scanner_device_path)
    except Exception:
        logger.exception(
            "Could not start scanner reader on %s; scans will be unavailable",
            settings.scanner_device_path,
        )
        _scanner = None

    yield

    if _scanner:
        _scanner.stop()


app = FastAPI(title="Inventory Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ammo.router)


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    products = list(
        db.scalars(
            select(AmmoProduct)
            .options(selectinload(AmmoProduct.identifiers))
            .where(AmmoProduct.deleted_at.is_(None))
            .order_by(AmmoProduct.manufacturer, AmmoProduct.cartridge)
        )
    )
    return templates.TemplateResponse(
        "index.html", {"request": request, "products": products}
    )


@app.websocket("/ws/scans")
async def scans_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Client sends nothing; this just keeps the connection open
            # and detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

