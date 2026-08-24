from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import AmmoPackageIdentifier, AmmoProduct, InventoryTransaction, TransactionType
from app.schemas import (
    AmmoProductCreate,
    AmmoProductOut,
    InventoryTransactionCreate,
    InventoryTransactionOut,
)

router = APIRouter(prefix="/api/ammo", tags=["ammo"])


def _with_identifiers(query):
    return query.options(selectinload(AmmoProduct.identifiers))


@router.get("", response_model=list[AmmoProductOut])
def list_products(db: Session = Depends(get_db)) -> list[AmmoProduct]:
    query = _with_identifiers(select(AmmoProduct)).where(AmmoProduct.deleted_at.is_(None))
    return list(db.scalars(query.order_by(AmmoProduct.manufacturer, AmmoProduct.cartridge)))


@router.post("", response_model=AmmoProductOut, status_code=201)
def create_product(payload: AmmoProductCreate, db: Session = Depends(get_db)) -> AmmoProduct:
    """Unknown-UPC confirmation: atomically creates the product, its first
    package identifier, and the initial RECEIVE transaction (spec §5.2)."""
    if db.scalar(select(AmmoPackageIdentifier).where(AmmoPackageIdentifier.upc == payload.upc)):
        raise HTTPException(status_code=409, detail="UPC already exists")

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

    identifier = AmmoPackageIdentifier(
        ammo_product_id=product.id,
        upc=payload.upc,
        rounds_per_package=payload.rounds_per_package,
    )
    db.add(identifier)

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


@router.get("/by-upc/{upc}", response_model=AmmoProductOut)
def get_product_by_upc(upc: str, db: Session = Depends(get_db)) -> AmmoProduct:
    identifier = db.scalar(
        select(AmmoPackageIdentifier).where(
            AmmoPackageIdentifier.upc == upc, AmmoPackageIdentifier.active.is_(True)
        )
    )
    if not identifier:
        raise HTTPException(status_code=404, detail="No product found for this UPC")
    product = db.scalar(_with_identifiers(select(AmmoProduct)).where(AmmoProduct.id == identifier.ammo_product_id))
    if not product:
        raise HTTPException(status_code=404, detail="No product found for this UPC")
    return product


@router.post("/{product_id}/transactions", response_model=InventoryTransactionOut, status_code=201)
def create_transaction(
    product_id: int, payload: InventoryTransactionCreate, db: Session = Depends(get_db)
) -> InventoryTransaction:
    """Confirmed IN/OUT/ADJUST against an existing product (spec §5.3, §6.2).

    Note: idempotency (client_request_id) and reversal are handled in a
    later phase.
    """
    product = db.get(AmmoProduct, product_id)
    if not product or product.is_deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.transaction_type == TransactionType.REMOVE and payload.box_delta > 0:
        box_delta = -payload.box_delta
    else:
        box_delta = payload.box_delta

    new_box_balance = product.box_quantity + box_delta
    if new_box_balance < 0:
        raise HTTPException(status_code=422, detail="Transaction would result in negative inventory")

    # Round delta uses the product's average package size across its active
    # identifiers as a stand-in until scan-driven transactions carry the
    # scanned identifier's exact rounds_per_package (see scanner integration).
    active_identifiers = [i for i in product.identifiers if i.active]
    rounds_per_package = active_identifiers[0].rounds_per_package if active_identifiers else 0
    round_delta = box_delta * rounds_per_package
    new_round_balance = product.round_quantity + round_delta

    transaction = InventoryTransaction(
        ammo_product_id=product.id,
        transaction_type=payload.transaction_type,
        box_delta=box_delta,
        round_delta=round_delta,
        previous_box_balance=product.box_quantity,
        new_box_balance=new_box_balance,
        previous_round_balance=product.round_quantity,
        new_round_balance=new_round_balance,
        notes=payload.notes,
    )
    db.add(transaction)
    product.box_quantity = new_box_balance
    product.round_quantity = new_round_balance

    db.commit()
    db.refresh(transaction)
    return transaction
