"""Audited editing, retirement, and restoration of ammunition metadata."""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AmmoPackageIdentifier, AmmoProduct, AuditEvent, InventoryTransaction
from app.schemas import AmmoPackageIdentifierUpdate, AmmoProductUpdate
from app.services.errors import DuplicateUpcError, ProductNotFoundError


class MetadataConflictError(Exception):
    pass


def update_product(db: Session, product_id: int, payload: AmmoProductUpdate) -> AmmoProduct:
    with db.begin():
        product = _product(db, product_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            _change(db, product, "AmmoProduct", field, value)
        from app.services import field_service
        field_service.validate_required_fields(db, product)
    db.refresh(product)
    return product


def update_identifier(db: Session, product_id: int, identifier_id: int, payload: AmmoPackageIdentifierUpdate) -> AmmoPackageIdentifier:
    with db.begin():
        product = _product(db, product_id)
        identifier = next((item for item in product.identifiers if item.id == identifier_id), None)
        if not identifier:
            raise ProductNotFoundError("Identifier not found")
        changes = payload.model_dump(exclude_unset=True, exclude={"confirm_rounds_per_package_change"})
        if "upc" in changes and changes["upc"] != identifier.upc:
            duplicate = db.scalar(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.upc == changes["upc"]))
            if duplicate:
                raise DuplicateUpcError(changes["upc"])
        if "rounds_per_package" in changes and changes["rounds_per_package"] != identifier.rounds_per_package:
            has_history = db.scalar(select(InventoryTransaction.id).where(InventoryTransaction.ammo_product_id == product.id).limit(1))
            if has_history and not payload.confirm_rounds_per_package_change:
                raise MetadataConflictError("Changing package size requires confirm_rounds_per_package_change=true")
        for field, value in changes.items():
            _change(db, identifier, "AmmoPackageIdentifier", field, value)
    db.refresh(identifier)
    return identifier


def soft_delete_product(db: Session, product_id: int) -> AmmoProduct:
    with db.begin():
        product = _product(db, product_id)
        if product.deleted_at is None:
            _change(db, product, "AmmoProduct", "deleted_at", datetime.now(UTC), action="DELETE")
        for identifier in product.identifiers:
            _change(db, identifier, "AmmoPackageIdentifier", "active", False, action="DELETE")
    db.refresh(product)
    return product


def restore_product(db: Session, product_id: int) -> AmmoProduct:
    with db.begin():
        product = _product(db, product_id, include_deleted=True)
        if product.deleted_at is None:
            raise MetadataConflictError("Product is not deleted")
        _change(db, product, "AmmoProduct", "deleted_at", None, action="RESTORE")
        for identifier in product.identifiers:
            _change(db, identifier, "AmmoPackageIdentifier", "active", True, action="RESTORE")
    db.refresh(product)
    return product


def _product(db: Session, product_id: int, *, include_deleted: bool = False) -> AmmoProduct:
    query = select(AmmoProduct).options(selectinload(AmmoProduct.identifiers)).where(AmmoProduct.id == product_id).with_for_update()
    if not include_deleted:
        query = query.where(AmmoProduct.deleted_at.is_(None))
    product = db.scalar(query)
    if not product:
        raise ProductNotFoundError("Product not found")
    return product


def _change(db: Session, entity, entity_type: str, field: str, value, *, action: str = "UPDATE") -> None:
    previous = getattr(entity, field)
    if previous == value:
        return
    setattr(entity, field, value)
    db.add(AuditEvent(
        entity_type=entity_type,
        entity_id=entity.id,
        action=action,
        field_key=field,
        old_value=_serialize(previous),
        new_value=_serialize(value),
        source_type="browser",
    ))


def _serialize(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, default=str, sort_keys=True)
