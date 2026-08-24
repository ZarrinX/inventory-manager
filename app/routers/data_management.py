"""Portable backup/restore and CSV data exchange endpoints."""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AmmoPackageIdentifier, AmmoProduct, AuditEvent, CustomFieldValue,
    DropdownOption, FieldDefinition, InventoryTransaction,
    InventoryViewPreference, Location, ScanEvent,
)
from app.schemas import InventoryTransactionCreate
from app.services import inventory_service
from app.services.errors import DuplicateUpcError, NegativeInventoryError

router = APIRouter(prefix="/api/data", tags=["data management"])

MODELS = {
    "field_definitions": FieldDefinition, "dropdown_options": DropdownOption,
    "locations": Location, "ammo_products": AmmoProduct,
    "ammo_package_identifiers": AmmoPackageIdentifier, "scan_events": ScanEvent,
    "inventory_transactions": InventoryTransaction, "custom_field_values": CustomFieldValue,
    "inventory_view_preferences": InventoryViewPreference, "audit_events": AuditEvent,
}
DELETE_ORDER = [AuditEvent, CustomFieldValue, InventoryTransaction, ScanEvent, AmmoPackageIdentifier, AmmoProduct, DropdownOption, FieldDefinition, InventoryViewPreference, Location]
RESTORE_ORDER = [FieldDefinition, DropdownOption, Location, AmmoProduct, AmmoPackageIdentifier, ScanEvent, InventoryTransaction, CustomFieldValue, InventoryViewPreference, AuditEvent]


def _value(value):
    if isinstance(value, Enum): return value.value
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    return value


def _rows(db: Session, model):
    return [{column.name: _value(getattr(row, column.name)) for column in model.__table__.columns} for row in db.scalars(select(model))]


@router.get("/backup")
def export_backup(db: Session = Depends(get_db)):
    return {"format": "inventory-manager-backup-v1", "data": {name: _rows(db, model) for name, model in MODELS.items()}}


@router.post("/restore")
def restore_backup(payload: dict, confirm_replace: bool = False, db: Session = Depends(get_db)):
    """Validate the entire backup before a single transactional replacement."""
    if not confirm_replace:
        raise HTTPException(status_code=422, detail="confirm_replace=true is required")
    data = _validate_backup(payload)
    try:
        with db.begin():
            for model in DELETE_ORDER:
                db.execute(delete(model))
            # Location parents are patched after all locations exist.
            parents = []
            for model in RESTORE_ORDER:
                name = next(key for key, value in MODELS.items() if value is model)
                for raw in data[name]:
                    values = _coerce(model, raw)
                    if model is Location and values.get("parent_id") is not None:
                        parents.append((values["id"], values.pop("parent_id")))
                    db.add(model(**values))
                db.flush()
            for location_id, parent_id in parents:
                db.get(Location, location_id).parent_id = parent_id
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Restore failed; no data was changed: {exc}") from exc
    return {"restored": {name: len(rows) for name, rows in data.items()}}


@router.get("/export/{kind}.csv")
def export_csv(kind: str, db: Session = Depends(get_db)):
    if kind == "inventory":
        headers = ["id", "manufacturer", "product_line", "manufacturer_sku", "cartridge", "bullet_weight_gr", "bullet_type", "box_quantity", "round_quantity", "upcs"]
        rows = [[p.id, p.manufacturer, p.product_line, p.manufacturer_sku, p.cartridge, p.bullet_weight_gr, p.bullet_type, p.box_quantity, p.round_quantity, ";".join(i.upc for i in p.identifiers)] for p in db.scalars(select(AmmoProduct))]
    elif kind == "transactions":
        headers = ["id", "ammo_product_id", "transaction_type", "box_delta", "round_delta", "previous_box_balance", "new_box_balance", "previous_round_balance", "new_round_balance", "source_type", "notes", "created_at"]
        rows = [[getattr(t, h) for h in headers] for t in db.scalars(select(InventoryTransaction))]
    elif kind == "audit":
        headers = ["id", "entity_type", "entity_id", "action", "field_key", "old_value", "new_value", "source_type", "source_id", "created_at"]
        rows = [[getattr(a, h) for h in headers] for a in db.scalars(select(AuditEvent))]
    else:
        raise HTTPException(status_code=404, detail="Export kind must be inventory, transactions, or audit")
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(rows)
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})


@router.post("/import/ammo.csv")
async def import_ammo_csv(file: UploadFile, commit: bool = False, db: Session = Depends(get_db)):
    try:
        rows = list(csv.DictReader((await file.read()).decode("utf-8-sig").splitlines()))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid CSV: {exc}") from exc
    required = {"upc", "manufacturer", "cartridge", "rounds_per_package"}
    errors, payloads, seen = [], [], set()
    for index, row in enumerate(rows, start=2):
        upc = (row.get("upc") or "").strip()
        if not required.issubset(row) or not all((row.get(key) or "").strip() for key in required): errors.append({"row": index, "error": "upc, manufacturer, cartridge, and rounds_per_package are required"}); continue
        if upc in seen or db.scalar(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.upc == upc)):
            errors.append({"row": index, "error": "Duplicate UPC"}); continue
        seen.add(upc)
        try:
            payloads.append(InventoryTransactionCreate(transaction_type="RECEIVE", new_product={"upc": upc, "manufacturer": row["manufacturer"].strip(), "product_line": _null(row.get("product_line")), "manufacturer_sku": _null(row.get("manufacturer_sku")), "cartridge": row["cartridge"].strip(), "bullet_weight_gr": _null(row.get("bullet_weight_gr")), "bullet_type": _null(row.get("bullet_type")), "rounds_per_package": int(row["rounds_per_package"]), "description": _null(row.get("description")), "notes": _null(row.get("notes")), "initial_box_quantity": int(row.get("initial_box_quantity") or 0)}))
        except Exception as exc: errors.append({"row": index, "error": str(exc)})
    result = {"dry_run": not commit, "rows": len(rows), "valid": len(payloads), "errors": errors}
    if errors or not commit: return result
    db.rollback()  # Clear read-only validation queries before service transactions.
    for payload in payloads:
        try:
            inventory_service.submit_transaction(db, payload, source_type="csv_import")
            db.rollback()  # submit_transaction refreshes its result after commit.
        except (DuplicateUpcError, NegativeInventoryError, inventory_service.TransactionTargetError) as exc: raise HTTPException(status_code=422, detail=f"Import failed; transactions before this row were committed: {exc}") from exc
    return {**result, "imported": len(payloads)}


def _null(value): return value.strip() or None if value else None


def _validate_backup(payload):
    if payload.get("format") != "inventory-manager-backup-v1" or not isinstance(payload.get("data"), dict):
        raise HTTPException(status_code=422, detail="Invalid backup format")
    data = payload["data"]
    if set(data) != set(MODELS) or any(not isinstance(data[name], list) for name in MODELS):
        raise HTTPException(status_code=422, detail="Backup is missing required entity collections")
    for name, model in MODELS.items():
        valid = {column.name for column in model.__table__.columns}
        for row in data[name]:
            if not isinstance(row, dict) or not set(row).issubset(valid):
                raise HTTPException(status_code=422, detail=f"Invalid row in {name}")
    return data


def _coerce(model, row):
    values = dict(row)
    for column in model.__table__.columns:
        value = values.get(column.name)
        if value is None: continue
        if column.name.endswith("_at") and isinstance(value, str): values[column.name] = datetime.fromisoformat(value)
        elif column.type.__class__.__name__ == "Numeric": values[column.name] = Decimal(str(value))
        elif hasattr(column.type, "enum_class") and isinstance(value, str): values[column.name] = column.type.enum_class(value)
    return values
