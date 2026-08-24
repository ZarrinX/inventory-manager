"""Business rules for creating ammunition products and inventory transactions.

Shared by the HTTP routes and the scanner integration so both act on the same
rules (spec §14, §22.5). Balance math and negative-inventory prevention live
here rather than in routers.
"""

from sqlalchemy.orm import Session

from app.models import AmmoPackageIdentifier, AmmoProduct, InventoryTransaction, TransactionType
from app.schemas import AmmoProductCreate
from app.services import identifier_service
from app.services.errors import DuplicateUpcError, NegativeInventoryError


def create_product_with_initial_transaction(
    db: Session, payload: AmmoProductCreate
) -> AmmoProduct:
    """Unknown-UPC confirmation: atomically creates the product, its first
    package identifier, and the initial RECEIVE transaction (spec §5.2)."""
    if identifier_service.resolve_identifier(db, payload.upc):
        raise DuplicateUpcError(payload.upc)

    product = AmmoProduct(
        manufacturer=payload.manufacturer,
        product_line=payload.product_line,
        manufacturer_sku=payload.manufacturer_sku,
        cartridge=payload.cartridge,
        bullet_weight_gr=payload.bullet_weight_gr,
        bullet_type=payload.bullet_type,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(product)
    db.flush()

    db.add(
        AmmoPackageIdentifier(
            ammo_product_id=product.id,
            upc=payload.upc,
            rounds_per_package=payload.rounds_per_package,
        )
    )

    round_delta = payload.initial_box_quantity * payload.rounds_per_package
    db.add(
        InventoryTransaction(
            ammo_product_id=product.id,
            transaction_type=TransactionType.RECEIVE,
            box_delta=payload.initial_box_quantity,
            round_delta=round_delta,
            previous_box_balance=0,
            new_box_balance=payload.initial_box_quantity,
            previous_round_balance=0,
            new_round_balance=round_delta,
        )
    )
    product.box_quantity = payload.initial_box_quantity
    product.round_quantity = round_delta

    db.commit()
    db.refresh(product)
    return product


def create_transaction(
    db: Session,
    product: AmmoProduct,
    transaction_type: TransactionType,
    box_delta: int,
    *,
    rounds_per_package: int | None = None,
    notes: str | None = None,
    scan_event_id: int | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
) -> InventoryTransaction:
    """Confirmed IN/OUT/ADJUST against an existing product (spec §5.3, §6.2).

    `rounds_per_package` should be the scanned/chosen identifier's value when
    known; falls back to the product's first active identifier otherwise.

    Note: idempotency (client_request_id) and reversal land in Phase 3.
    """
    if transaction_type == TransactionType.REMOVE and box_delta > 0:
        box_delta = -box_delta

    new_box_balance = product.box_quantity + box_delta
    if new_box_balance < 0:
        raise NegativeInventoryError(
            f"Product {product.id}: {box_delta} would drop box_quantity below 0"
        )

    if rounds_per_package is None:
        active_identifiers = [i for i in product.identifiers if i.active]
        rounds_per_package = active_identifiers[0].rounds_per_package if active_identifiers else 0

    round_delta = box_delta * rounds_per_package
    new_round_balance = product.round_quantity + round_delta

    transaction = InventoryTransaction(
        ammo_product_id=product.id,
        scan_event_id=scan_event_id,
        transaction_type=transaction_type,
        box_delta=box_delta,
        round_delta=round_delta,
        previous_box_balance=product.box_quantity,
        new_box_balance=new_box_balance,
        previous_round_balance=product.round_quantity,
        new_round_balance=new_round_balance,
        source_type=source_type,
        source_id=source_id,
        notes=notes,
    )
    db.add(transaction)
    product.box_quantity = new_box_balance
    product.round_quantity = new_round_balance

    db.commit()
    db.refresh(transaction)
    return transaction
