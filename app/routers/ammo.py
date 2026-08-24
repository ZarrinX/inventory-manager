from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import AmmoProduct, InventoryTransaction
from app.schemas import (
    AmmoProductCreate,
    AmmoProductOut,
    InventoryTransactionCreate,
    InventoryTransactionOut,
)
from app.services import identifier_service, inventory_service
from app.services.errors import DuplicateUpcError, NegativeInventoryError

router = APIRouter(prefix="/api/ammo", tags=["ammo"])


def _with_identifiers(query):
    return query.options(selectinload(AmmoProduct.identifiers))


@router.get("", response_model=list[AmmoProductOut])
def list_products(db: Session = Depends(get_db)) -> list[AmmoProduct]:
    query = _with_identifiers(select(AmmoProduct)).where(AmmoProduct.deleted_at.is_(None))
    return list(db.scalars(query.order_by(AmmoProduct.manufacturer, AmmoProduct.cartridge)))


@router.post("", response_model=AmmoProductOut, status_code=201)
def create_product(payload: AmmoProductCreate, db: Session = Depends(get_db)) -> AmmoProduct:
    try:
        return inventory_service.create_product_with_initial_transaction(db, payload)
    except DuplicateUpcError as exc:
        raise HTTPException(status_code=409, detail="UPC already exists") from exc


@router.get("/by-upc/{upc}", response_model=AmmoProductOut)
def get_product_by_upc(upc: str, db: Session = Depends(get_db)) -> AmmoProduct:
    product = identifier_service.resolve_upc(db, upc)
    if not product:
        raise HTTPException(status_code=404, detail="No product found for this UPC")
    return product


@router.post("/{product_id}/transactions", response_model=InventoryTransactionOut, status_code=201)
def create_transaction(
    product_id: int, payload: InventoryTransactionCreate, db: Session = Depends(get_db)
) -> InventoryTransaction:
    product = db.scalar(_with_identifiers(select(AmmoProduct)).where(AmmoProduct.id == product_id))
    if not product or product.is_deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        return inventory_service.create_transaction(
            db,
            product,
            transaction_type=payload.transaction_type,
            box_delta=payload.box_delta,
            notes=payload.notes,
            source_type="browser",
        )
    except NegativeInventoryError as exc:
        raise HTTPException(status_code=422, detail="Transaction would result in negative inventory") from exc
