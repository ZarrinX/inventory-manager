from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InventoryViewPreference
from app.schemas import InventoryViewPreferenceOut, InventoryViewPreferenceUpdate

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

DEFAULT_COLUMNS = ["manufacturer", "product_line", "cartridge", "box_quantity", "round_quantity"]
VALID_COLUMNS = {
    "manufacturer", "product_line", "manufacturer_sku", "cartridge", "bullet_weight_gr",
    "bullet_type", "box_quantity", "round_quantity",
}


def _default_view(db: Session) -> InventoryViewPreference:
    preference = db.scalar(select(InventoryViewPreference).where(InventoryViewPreference.is_default.is_(True)))
    if preference:
        return preference
    preference = InventoryViewPreference(visible_columns=DEFAULT_COLUMNS, column_order=DEFAULT_COLUMNS, sort_field="manufacturer", sort_direction="asc", page_size=50)
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


def _clean_columns(columns: list[str]) -> list[str]:
    return [column for column in columns if column in VALID_COLUMNS]


@router.get("/inventory-view", response_model=InventoryViewPreferenceOut)
def get_inventory_view(db: Session = Depends(get_db)):
    return _default_view(db)


@router.put("/inventory-view", response_model=InventoryViewPreferenceOut)
def update_inventory_view(payload: InventoryViewPreferenceUpdate, db: Session = Depends(get_db)):
    preference = _default_view(db)
    visible = _clean_columns(payload.visible_columns)
    order = _clean_columns(payload.column_order)
    if not visible or not order:
        raise HTTPException(status_code=422, detail="At least one valid column is required")
    preference.visible_columns = visible
    preference.column_order = order
    preference.sort_field = payload.sort_field if payload.sort_field in VALID_COLUMNS else "manufacturer"
    preference.sort_direction = "desc" if payload.sort_direction == "desc" else "asc"
    preference.page_size = payload.page_size
    db.commit()
    db.refresh(preference)
    return preference


@router.post("/inventory-view/reset", response_model=InventoryViewPreferenceOut)
def reset_inventory_view(db: Session = Depends(get_db)):
    preference = _default_view(db)
    preference.visible_columns = DEFAULT_COLUMNS
    preference.column_order = DEFAULT_COLUMNS
    preference.sort_field = "manufacturer"
    preference.sort_direction = "asc"
    preference.page_size = 50
    db.commit()
    db.refresh(preference)
    return preference
