"""Confirmed inventory mutations and their immutable transaction history."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AmmoPackageIdentifier, AmmoProduct, InventoryTransaction, Location, ScanEvent, ScanStatus, TransactionType
from app.schemas import InventoryTransactionCreate, TransactionReverseRequest
from app.services import identifier_service
from app.services.errors import DuplicateUpcError, NegativeInventoryError


class TransactionTargetError(Exception):
    pass


@dataclass
class TransactionResult:
    transaction: InventoryTransaction
    product: AmmoProduct
    next_scan: object | None
    idempotent: bool = False


def submit_transaction(db: Session, payload: InventoryTransactionCreate, *, source_type: str = "browser") -> TransactionResult:
    """Atomically create a confirmed mutation and consume its active scan."""
    with db.begin():
        existing = _idempotent_transaction(db, payload.client_request_id)
        if existing:
            return TransactionResult(existing, _locked_product(db, existing.ammo_product_id), None, True)

        try:
            scan = _locked_scan(db, payload.scan_event_id) if payload.scan_event_id else None
        except TransactionTargetError:
            # A concurrent retry may have waited on the scan row until the
            # first request committed. Re-check its idempotency key after the
            # wait so it receives the original result rather than a conflict.
            existing = _idempotent_transaction(db, payload.client_request_id)
            if not existing:
                raise
            return TransactionResult(existing, _locked_product(db, existing.ammo_product_id), None, True)
        if payload.new_product:
            product, identifier = _create_product(db, payload.new_product)
            if scan and scan.payload != payload.new_product.upc:
                raise TransactionTargetError("Scan UPC does not match new_product.upc")
            box_delta = payload.new_product.initial_box_quantity
        else:
            product, identifier = _resolve_existing_target(db, payload, scan)
            box_delta = _normalize_box_delta(payload.transaction_type, payload.box_delta or 0)

        transaction = _append_transaction(
            db, product, payload.transaction_type, box_delta,
            rounds_per_package=identifier.rounds_per_package,
            scan_event_id=scan.id if scan else None, notes=payload.notes,
            source_type=source_type, client_request_id=payload.client_request_id,
        )
        next_event = _complete_scan_and_promote_next(db, scan) if scan else None

    db.refresh(transaction)
    db.refresh(product)
    if next_event:
        from app.services import scan_service
        next_scan = scan_service.result_for_event(db, next_event)
    else:
        next_scan = None
    return TransactionResult(transaction, product, next_scan)


def reverse_transaction(db: Session, transaction_id: int, payload: TransactionReverseRequest, *, source_type: str = "browser") -> TransactionResult:
    """Create a compensating immutable transaction; never edit the original."""
    with db.begin():
        existing = _idempotent_transaction(db, payload.client_request_id)
        if existing:
            return TransactionResult(existing, _locked_product(db, existing.ammo_product_id), None, True)
        original = db.scalar(select(InventoryTransaction).where(InventoryTransaction.id == transaction_id).with_for_update())
        if not original:
            raise TransactionTargetError("Transaction not found")
        if db.scalar(select(InventoryTransaction.id).where(InventoryTransaction.reverses_transaction_id == original.id)):
            raise TransactionTargetError("Transaction has already been reversed")
        product = _locked_product(db, original.ammo_product_id)
        transaction_type = (
            TransactionType.REMOVE if original.transaction_type == TransactionType.RECEIVE
            else TransactionType.RECEIVE if original.transaction_type == TransactionType.REMOVE
            else TransactionType.ADJUST
        )
        reversal = _append_transaction(
            db, product, transaction_type, -original.box_delta,
            round_delta_override=-original.round_delta, notes=payload.notes,
            source_type=source_type, client_request_id=payload.client_request_id,
            reverses_transaction_id=original.id,
        )
    db.refresh(reversal)
    db.refresh(product)
    return TransactionResult(reversal, product, None)


def _create_product(db: Session, payload):
    if db.scalar(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.upc == payload.upc)):
        raise DuplicateUpcError(payload.upc)
    if payload.storage_location_id and not db.scalar(select(Location.id).where(Location.id == payload.storage_location_id, Location.active.is_(True))):
        raise TransactionTargetError("Storage location not found or inactive")
    product = AmmoProduct(
        manufacturer=payload.manufacturer, product_line=payload.product_line,
        manufacturer_sku=payload.manufacturer_sku, cartridge=payload.cartridge,
        bullet_weight_gr=payload.bullet_weight_gr, bullet_type=payload.bullet_type,
        description=payload.description, notes=payload.notes, storage_location_id=payload.storage_location_id,
    )
    db.add(product)
    db.flush()
    from app.services import field_service
    field_service.apply_custom_field_values(db, product.id, payload.custom_fields, creating=True)
    identifier = AmmoPackageIdentifier(ammo_product_id=product.id, upc=payload.upc, rounds_per_package=payload.rounds_per_package)
    db.add(identifier)
    # Required system UPC/rounds checks query the database, so make the new
    # package identifier visible before evaluating the field rules.
    db.flush()
    field_service.validate_required_fields(db, product)
    return product, identifier


def _resolve_existing_target(db: Session, payload, scan: ScanEvent | None):
    if scan:
        identifier = identifier_service.resolve_identifier(db, scan.payload)
        if not identifier:
            raise TransactionTargetError("The scanned UPC is no longer active")
        product = _locked_product(db, identifier.ammo_product_id)
        if payload.ammo_product_id and payload.ammo_product_id != product.id:
            raise TransactionTargetError("Scan does not belong to the requested product")
        return product, identifier
    identifier = identifier_service.resolve_identifier(db, payload.upc) if payload.upc else None
    if identifier:
        return _locked_product(db, identifier.ammo_product_id), identifier
    if payload.ammo_product_id:
        product = _locked_product(db, payload.ammo_product_id)
        identifier = next((item for item in product.identifiers if item.active), None)
        if identifier:
            return product, identifier
    raise TransactionTargetError("Product not found or has no active package identifier")


def _locked_product(db: Session, product_id: int) -> AmmoProduct:
    product = db.scalar(select(AmmoProduct).options(selectinload(AmmoProduct.identifiers)).where(AmmoProduct.id == product_id, AmmoProduct.deleted_at.is_(None)).with_for_update())
    if not product:
        raise TransactionTargetError("Product not found")
    return product


def _locked_scan(db: Session, scan_id: int) -> ScanEvent:
    scan = db.scalar(select(ScanEvent).where(ScanEvent.id == scan_id).with_for_update())
    if not scan or scan.status != ScanStatus.RESOLVED:
        raise TransactionTargetError("Scan is not the active unresolved scan")
    return scan


def _normalize_box_delta(transaction_type: TransactionType, box_delta: int) -> int:
    if transaction_type == TransactionType.RECEIVE:
        return abs(box_delta)
    if transaction_type == TransactionType.REMOVE:
        return -abs(box_delta)
    return box_delta


def _append_transaction(db: Session, product: AmmoProduct, transaction_type: TransactionType, box_delta: int, *, rounds_per_package: int | None = None, round_delta_override: int | None = None, scan_event_id: int | None = None, notes: str | None = None, source_type: str | None = None, client_request_id: str | None = None, reverses_transaction_id: int | None = None) -> InventoryTransaction:
    round_delta = round_delta_override if round_delta_override is not None else box_delta * (rounds_per_package or 0)
    new_boxes, new_rounds = product.box_quantity + box_delta, product.round_quantity + round_delta
    if new_boxes < 0 or new_rounds < 0:
        raise NegativeInventoryError("Transaction would result in negative inventory")
    transaction = InventoryTransaction(
        ammo_product_id=product.id, scan_event_id=scan_event_id, transaction_type=transaction_type,
        box_delta=box_delta, round_delta=round_delta, previous_box_balance=product.box_quantity,
        new_box_balance=new_boxes, previous_round_balance=product.round_quantity,
        new_round_balance=new_rounds, source_type=source_type, client_request_id=client_request_id,
        reverses_transaction_id=reverses_transaction_id, notes=notes,
    )
    db.add(transaction)
    product.box_quantity, product.round_quantity = new_boxes, new_rounds
    return transaction


def _complete_scan_and_promote_next(db: Session, scan: ScanEvent) -> ScanEvent | None:
    scan.status = ScanStatus.COMPLETED
    next_event = db.scalar(select(ScanEvent).where(ScanEvent.status == ScanStatus.RECEIVED).order_by(ScanEvent.scanned_at, ScanEvent.id).with_for_update().limit(1))
    if next_event:
        next_event.status = ScanStatus.RESOLVED
    return next_event


def _idempotent_transaction(db: Session, client_request_id: str | None):
    return db.scalar(select(InventoryTransaction).where(InventoryTransaction.client_request_id == client_request_id)) if client_request_id else None
