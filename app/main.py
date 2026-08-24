import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.broadcast import manager, scan_payload
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import AmmoProduct, AuditEvent, FieldDefinition, Location
from app.routers import ammo, audit, data_management, fields, locations, preferences, scans, transactions
from app.scanner import ScannerReader
from app.services import scan_service

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

_scanner: ScannerReader | None = None


def _handle_scan(payload: str, loop: asyncio.AbstractEventLoop) -> None:
    """Runs on the scanner's background thread: records the scan event and
    schedules a broadcast on the app's event loop. Never mutates inventory
    itself (spec §3.1) — that only happens via a confirmed transaction."""
    db: Session = SessionLocal()
    try:
        result = scan_service.record_scan(db, payload)
    except Exception:
        db.rollback()
        logger.exception("Could not persist scanner payload; scan was not broadcast")
        return
    finally:
        db.close()

    if result.event is not None:
        asyncio.run_coroutine_threadsafe(manager.broadcast(scan_payload(result)), loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scanner
    # Schema is managed by Alembic migrations (see alembic/), not created here.

    loop = asyncio.get_running_loop()
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
app.include_router(scans.router)
app.include_router(transactions.router)
app.include_router(audit.router)
app.include_router(preferences.router)
app.include_router(fields.router)
app.include_router(locations.router)
app.include_router(data_management.router)


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
    form_fields = list(
        db.scalars(
            select(FieldDefinition).options(selectinload(FieldDefinition.options))
            .where(FieldDefinition.enabled.is_(True))
            .order_by(FieldDefinition.sort_order)
        )
    )
    locations_for_form = list(db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.name)))
    return templates.TemplateResponse(
        "index.html", {"request": request, "products": products, "form_fields": form_fields, "locations": locations_for_form}
    )


@app.get("/api/scanners")
def scanner_status():
    return {
        "connected": _scanner.connected if _scanner else False,
        "last_scan_at": _scanner.last_scan_at.isoformat() if _scanner and _scanner.last_scan_at else None,
    }


@app.get("/audit")
def audit_history(
    request: Request,
    entity_type: str | None = None,
    entity_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(250)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditEvent.entity_id == entity_id)
    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "events": list(db.scalars(query)), "entity_type": entity_type, "entity_id": entity_id},
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
