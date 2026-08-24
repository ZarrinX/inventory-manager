"""Tracks connected WebSocket clients and broadcasts scan events to them."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        async with self._lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                await self.disconnect(connection)


manager = ConnectionManager()


def scan_payload(result: Any) -> dict[str, Any]:
    """Serialize a scan using the WebSocket contract from spec §13."""
    scan = result.event
    assert scan is not None
    product = result.product
    identifier = result.identifier
    payload: dict[str, Any] = {
        "event": "barcode_scanned" if result.disposition == "active" else f"scan_{result.disposition}",
        "scan_id": scan.id,
        "code": scan.payload,
        "format": scan.barcode_format or "UNKNOWN",
        "timestamp": scan.scanned_at.isoformat(),
        "queue_depth": result.queue_depth,
        "resolution": {"known": product is not None},
    }
    if product:
        payload["resolution"]["product"] = {
            "id": product.id,
            "manufacturer": product.manufacturer,
            "product_line": product.product_line,
            "cartridge": product.cartridge,
            "bullet_weight_gr": product.bullet_weight_gr,
            "bullet_type": product.bullet_type,
            "rounds_per_box": identifier.rounds_per_package if identifier else None,
            "upc": scan.payload,
            "box_quantity": product.box_quantity,
            "round_quantity": product.round_quantity,
        }
    return payload
