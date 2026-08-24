import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broadcast import manager
from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import Item, ScanEvent
from app.routers import items
from app.scanner import ScannerReader

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

_scanner: ScannerReader | None = None


def _handle_scan(payload: str, loop: asyncio.AbstractEventLoop) -> None:
    """Runs on the scanner's background thread: persists the scan and
    schedules a broadcast on the app's event loop."""
    db: Session = SessionLocal()
    try:
        item = db.scalar(select(Item).where(Item.upc == payload))
        event = ScanEvent(upc=payload, item_id=item.id if item else None)
        db.add(event)
        db.commit()

        result = {
            "upc": payload,
            "scanned_at": event.scanned_at.isoformat(),
            "item": {
                "id": item.id,
                "upc": item.upc,
                "name": item.name,
                "description": item.description,
                "quantity": item.quantity,
            }
            if item
            else None,
        }
    finally:
        db.close()

    asyncio.run_coroutine_threadsafe(manager.broadcast(result), loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scanner
    Base.metadata.create_all(bind=engine)

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
app.include_router(items.router)


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    all_items = list(db.scalars(select(Item).order_by(Item.name)))
    return templates.TemplateResponse(
        "index.html", {"request": request, "items": all_items}
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

