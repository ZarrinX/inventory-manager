"""Scan lifecycle: recording a scan event and resolving it against inventory.

Never mutates inventory itself (spec §3.1) — only records what was scanned
and, if resolvable, which product it points to. The scan queue and debounce
logic (spec §24.5, §24.6) are Phase 3 additions to this module.
"""

from sqlalchemy.orm import Session

from app.models import AmmoProduct, ScanEvent
from app.services import identifier_service


def record_scan(db: Session, payload: str, scanner_id: str | None = None) -> tuple[ScanEvent, AmmoProduct | None]:
    product = identifier_service.resolve_upc(db, payload)

    event = ScanEvent(
        payload=payload,
        ammo_product_id=product.id if product else None,
        scanner_id=scanner_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return event, product
