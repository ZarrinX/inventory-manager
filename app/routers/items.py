from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Item
from app.schemas import ItemAdjust, ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)) -> list[Item]:
    return list(db.scalars(select(Item).order_by(Item.name)))


@router.post("", response_model=ItemOut, status_code=201)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> Item:
    if db.scalar(select(Item).where(Item.upc == payload.upc)):
        raise HTTPException(status_code=409, detail="Item with this UPC already exists")
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{upc}", response_model=ItemOut)
def get_item(upc: str, db: Session = Depends(get_db)) -> Item:
    item = db.scalar(select(Item).where(Item.upc == upc))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{upc}", response_model=ItemOut)
def update_item(upc: str, payload: ItemUpdate, db: Session = Depends(get_db)) -> Item:
    item = db.scalar(select(Item).where(Item.upc == upc))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{upc}/adjust", response_model=ItemOut)
def adjust_item_quantity(upc: str, payload: ItemAdjust, db: Session = Depends(get_db)) -> Item:
    item = db.scalar(select(Item).where(Item.upc == upc))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.quantity = max(0, item.quantity + payload.delta)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{upc}", status_code=204)
def delete_item(upc: str, db: Session = Depends(get_db)) -> None:
    item = db.scalar(select(Item).where(Item.upc == upc))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
