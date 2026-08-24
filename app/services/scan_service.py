"""Scan lifecycle, queueing, and UPC resolution.

A scan is informational until a later, confirmed transaction consumes it.
This module owns the active-scan/queue state so another scan can never
silently replace an unresolved interaction.
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AmmoPackageIdentifier, AmmoProduct, ScanEvent, ScanStatus
from app.services import identifier_service

logger = logging.getLogger(__name__)

MAX_QUEUE_DEPTH = 5
DEBOUNCE_SECONDS = 0.5


class ScanDisposition(StrEnum):
    ACTIVE = "active"
    QUEUED = "queued"
    DUPLICATE = "duplicate"
    OVERFLOW = "overflow"


class ScanTransitionError(Exception):
    """The requested scan is missing or is no longer the active scan."""


@dataclass
class ScanResult:
    disposition: ScanDisposition
    event: ScanEvent | None
    product: AmmoProduct | None
    identifier: AmmoPackageIdentifier | None
    queue_depth: int


@dataclass
class ScanAdvanceResult:
    finished_event: ScanEvent
    next_scan: ScanResult | None


class ScanWorkflow:
    """Process-local coordination for one scanner workflow.

    The database remains the durable source of scan history and statuses. The
    lock only protects concurrent scanner callbacks in this application
    process; a future multi-process deployment should replace it with a
    database/advisory lock and terminal routing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_accepted: dict[tuple[str, str], float] = {}

    def record(
        self, db: Session, payload: str, scanner_id: str | None = None
    ) -> ScanResult:
        source = scanner_id or "default"
        key = (source, payload)
        now = time.monotonic()

        with self._lock:
            previous = self._last_accepted.get(key)
            if previous is not None and now - previous < DEBOUNCE_SECONDS:
                logger.info("Suppressed duplicate scan from %s: %s", source, payload)
                return ScanResult(ScanDisposition.DUPLICATE, None, None, None, self._queue_depth(db))

            active = db.scalar(
                select(ScanEvent.id).where(ScanEvent.status == ScanStatus.RESOLVED).limit(1)
            )
            queued = self._queue_depth(db)
            identifier = identifier_service.resolve_identifier(db, payload)
            product = self._product_for_identifier(db, identifier)

            if active is not None and queued >= MAX_QUEUE_DEPTH:
                event = ScanEvent(
                    payload=payload,
                    ammo_product_id=product.id if product else None,
                    scanner_id=scanner_id,
                    status=ScanStatus.FAILED,
                )
                db.add(event)
                db.commit()
                db.refresh(event)
                logger.warning("Rejected scan because the pending queue is full: %s", payload)
                self._last_accepted[key] = now
                return ScanResult(ScanDisposition.OVERFLOW, event, product, identifier, queued)

            event = ScanEvent(
                payload=payload,
                ammo_product_id=product.id if product else None,
                scanner_id=scanner_id,
                status=ScanStatus.RESOLVED if active is None else ScanStatus.RECEIVED,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            self._last_accepted[key] = now

            disposition = ScanDisposition.ACTIVE if active is None else ScanDisposition.QUEUED
            return ScanResult(disposition, event, product, identifier, queued + (1 if active is not None else 0))

    def finish(
        self, db: Session, scan_id: int, status: ScanStatus
    ) -> ScanAdvanceResult:
        if status not in (ScanStatus.CANCELED, ScanStatus.COMPLETED):
            raise ValueError("Only canceled or completed scans can be finished")

        with self._lock:
            event = db.scalar(select(ScanEvent).where(ScanEvent.id == scan_id))
            if event is None:
                raise ScanTransitionError("Scan not found")
            if event.status != ScanStatus.RESOLVED:
                raise ScanTransitionError("Scan is not the active unresolved scan")

            event.status = status
            next_event = db.scalar(
                select(ScanEvent)
                .where(ScanEvent.status == ScanStatus.RECEIVED)
                .order_by(ScanEvent.scanned_at, ScanEvent.id)
                .limit(1)
            )
            if next_event:
                next_event.status = ScanStatus.RESOLVED
            db.commit()
            db.refresh(event)

            if not next_event:
                return ScanAdvanceResult(event, None)

            db.refresh(next_event)
            identifier = identifier_service.resolve_identifier(db, next_event.payload)
            product = self._product_for_identifier(db, identifier)
            return ScanAdvanceResult(
                event,
                ScanResult(
                    ScanDisposition.ACTIVE,
                    next_event,
                    product,
                    identifier,
                    self._queue_depth(db),
                ),
            )

    @staticmethod
    def _product_for_identifier(
        db: Session, identifier: AmmoPackageIdentifier | None
    ) -> AmmoProduct | None:
        if identifier is None:
            return None
        return db.scalar(
            select(AmmoProduct)
            .options(selectinload(AmmoProduct.identifiers))
            .where(AmmoProduct.id == identifier.ammo_product_id)
        )

    @staticmethod
    def _queue_depth(db: Session) -> int:
        return len(
            db.scalars(select(ScanEvent.id).where(ScanEvent.status == ScanStatus.RECEIVED)).all()
        )


workflow = ScanWorkflow()


def record_scan(db: Session, payload: str, scanner_id: str | None = None) -> ScanResult:
    return workflow.record(db, payload, scanner_id)


def cancel_scan(db: Session, scan_id: int) -> ScanAdvanceResult:
    return workflow.finish(db, scan_id, ScanStatus.CANCELED)


def complete_scan(db: Session, scan_id: int) -> ScanAdvanceResult:
    """Advance a scan after its confirmed transaction has been committed."""
    return workflow.finish(db, scan_id, ScanStatus.COMPLETED)


def result_for_event(db: Session, event: ScanEvent) -> ScanResult:
    """Build the active-scan broadcast payload after an atomic transaction."""
    identifier = identifier_service.resolve_identifier(db, event.payload)
    product = workflow._product_for_identifier(db, identifier)
    return ScanResult(ScanDisposition.ACTIVE, event, product, identifier, workflow._queue_depth(db))


def active_scan(db: Session) -> ScanResult | None:
    """Return the durable active scan so reconnecting clients can revalidate."""
    event = db.scalar(
        select(ScanEvent)
        .where(ScanEvent.status == ScanStatus.RESOLVED)
        .order_by(ScanEvent.scanned_at, ScanEvent.id)
        .limit(1)
    )
    return result_for_event(db, event) if event else None
