from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.broadcast import manager, scan_payload
from app.db import get_db
from app.models import AmmoPackageIdentifier, AmmoProduct, InventoryTransaction, TransactionType
from app.schemas import (
    InventoryTransactionCreate,
    TransactionHistoryPage,
    TransactionReverseRequest,
    TransactionSubmissionOut,
)
from app.services import inventory_service
from app.services.errors import DuplicateUpcError, NegativeInventoryError

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _response(result: inventory_service.TransactionResult) -> dict:
    return {
        "transaction": result.transaction,
        "product": result.product,
        "idempotent": result.idempotent,
    }


@router.get("", response_model=TransactionHistoryPage)
def list_transactions(
    search: str | None = None,
    transaction_type: TransactionType | None = None,
    ammo_product_id: int | None = None,
    manufacturer: str | None = None,
    cartridge: str | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=100),
    db: Session = Depends(get_db),
):
    """Global transaction history with server-side filtering and sorting."""
    query = select(InventoryTransaction, AmmoProduct).join(AmmoProduct, AmmoProduct.id == InventoryTransaction.ammo_product_id)
    if transaction_type:
        query = query.where(InventoryTransaction.transaction_type == transaction_type)
    if ammo_product_id:
        query = query.where(InventoryTransaction.ammo_product_id == ammo_product_id)
    if manufacturer:
        query = query.where(AmmoProduct.manufacturer.ilike(f"%{manufacturer}%"))
    if cartridge:
        query = query.where(AmmoProduct.cartridge.ilike(f"%{cartridge}%"))
    if source:
        query = query.where(InventoryTransaction.source_type.ilike(f"%{source}%"))
    if date_from:
        query = query.where(InventoryTransaction.created_at >= date_from)
    if date_to:
        query = query.where(InventoryTransaction.created_at < date_to + timedelta(days=1))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            AmmoProduct.manufacturer.ilike(pattern), AmmoProduct.product_line.ilike(pattern),
            AmmoProduct.cartridge.ilike(pattern), AmmoProduct.manufacturer_sku.ilike(pattern),
            InventoryTransaction.notes.ilike(pattern), InventoryTransaction.source_type.ilike(pattern),
            exists(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.ammo_product_id == AmmoProduct.id, AmmoPackageIdentifier.upc.ilike(pattern))),
        ))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    sortable = {
        "created_at": InventoryTransaction.created_at, "transaction_type": InventoryTransaction.transaction_type,
        "box_delta": InventoryTransaction.box_delta, "round_delta": InventoryTransaction.round_delta,
        "manufacturer": AmmoProduct.manufacturer, "cartridge": AmmoProduct.cartridge,
        "source": InventoryTransaction.source_type,
    }
    order = sortable.get(sort, InventoryTransaction.created_at)
    order = order.desc() if direction.lower() == "desc" else order.asc()
    rows = db.execute(query.order_by(order, InventoryTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    reversed_ids = set(db.scalars(select(InventoryTransaction.reverses_transaction_id).where(InventoryTransaction.reverses_transaction_id.is_not(None))))
    return {
        "items": [
            {
                **{
                    "id": transaction.id, "ammo_product_id": transaction.ammo_product_id,
                    "transaction_type": transaction.transaction_type, "box_delta": transaction.box_delta,
                    "round_delta": transaction.round_delta, "previous_box_balance": transaction.previous_box_balance,
                    "new_box_balance": transaction.new_box_balance, "previous_round_balance": transaction.previous_round_balance,
                    "new_round_balance": transaction.new_round_balance, "notes": transaction.notes,
                    "created_at": transaction.created_at, "source_type": transaction.source_type,
                    "source_id": transaction.source_id, "reverses_transaction_id": transaction.reverses_transaction_id,
                    "is_reversed": transaction.id in reversed_ids,
                },
                "manufacturer": product.manufacturer, "product_line": product.product_line, "cartridge": product.cartridge,
            }
            for transaction, product in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("", response_model=TransactionSubmissionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(payload: InventoryTransactionCreate, response: Response, db: Session = Depends(get_db)):
    try:
        result = inventory_service.submit_transaction(db, payload)
    except DuplicateUpcError as exc:
        raise HTTPException(status_code=409, detail="UPC already exists") from exc
    except NegativeInventoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except inventory_service.TransactionTargetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.idempotent:
        response.status_code = status.HTTP_200_OK
    if result.next_scan:
        await manager.broadcast(scan_payload(result.next_scan))
    return _response(result)


@router.post("/{transaction_id}/reverse", response_model=TransactionSubmissionOut, status_code=status.HTTP_201_CREATED)
async def reverse_transaction(transaction_id: int, payload: TransactionReverseRequest, response: Response, db: Session = Depends(get_db)):
    try:
        result = inventory_service.reverse_transaction(db, transaction_id, payload)
    except NegativeInventoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except inventory_service.TransactionTargetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.idempotent:
        response.status_code = status.HTTP_200_OK
    return _response(result)
