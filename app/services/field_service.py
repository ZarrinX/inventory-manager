"""Configurable field definitions, dropdowns, and typed custom values."""

import json
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AmmoPackageIdentifier, AuditEvent, CustomFieldValue, DropdownOption, FieldControlType, FieldDefinition, FieldValueType
from app.schemas import (
    DropdownOptionCreate, DropdownOptionUpdate, FieldDefinitionCreate,
    FieldDefinitionUpdate,
)


class FieldConfigurationError(Exception):
    pass


def list_fields(db: Session):
    return list(db.scalars(select(FieldDefinition).options(selectinload(FieldDefinition.options)).order_by(FieldDefinition.sort_order, FieldDefinition.id)))


def create_field(db: Session, payload: FieldDefinitionCreate):
    with db.begin():
        if db.scalar(select(FieldDefinition.id).where(FieldDefinition.field_key == payload.field_key)):
            raise FieldConfigurationError("Field key already exists")
        field = FieldDefinition(**payload.model_dump(), system_field=False)
        db.add(field); db.flush()
        _audit(db, field, "CREATE", None, None, payload.model_dump())
    db.refresh(field)
    return field


def update_field(db: Session, field_id: int, payload: FieldDefinitionUpdate):
    with db.begin():
        field = _field(db, field_id)
        changes = payload.model_dump(exclude_unset=True)
        if ("field_type" in changes or "value_type" in changes) and _has_values(db, field.id):
            raise FieldConfigurationError("Field type/value type cannot change after values exist; create a replacement field and retire this one")
        if field.system_field:
            for protected in ("field_type", "value_type"):
                if protected in changes and changes[protected] != getattr(field, protected):
                    raise FieldConfigurationError("System field type cannot change")
            if field.field_key in {"upc", "rounds_per_package"} and changes.get("required") is False:
                raise FieldConfigurationError("This system field is permanently required")
        for key, value in changes.items():
            old = getattr(field, key)
            if old != value:
                setattr(field, key, value); _audit(db, field, "UPDATE", key, old, value)
    db.refresh(field)
    return field


def delete_field(db: Session, field_id: int):
    with db.begin():
        field = _field(db, field_id)
        if field.system_field:
            raise FieldConfigurationError("System fields cannot be deleted")
        if _has_values(db, field.id):
            if field.enabled:
                field.enabled = False; _audit(db, field, "RETIRE", "enabled", True, False)
            return field
        _audit(db, field, "DELETE", None, field.field_key, None)
        db.delete(field)
        return None


def create_option(db: Session, field_id: int, payload: DropdownOptionCreate):
    with db.begin():
        field = _field(db, field_id)
        if field.field_type != FieldControlType.DROPDOWN:
            raise FieldConfigurationError("Options are only valid for dropdown fields")
        if db.scalar(select(DropdownOption.id).where(DropdownOption.field_definition_id == field.id, DropdownOption.stable_key == payload.stable_key)):
            raise FieldConfigurationError("Option key already exists")
        option = DropdownOption(field_definition_id=field.id, **payload.model_dump())
        db.add(option); db.flush(); _audit(db, option, "CREATE", None, None, payload.model_dump())
    db.refresh(option)
    return option


def update_option(db: Session, field_id: int, option_id: int, payload: DropdownOptionUpdate):
    with db.begin():
        option = db.scalar(select(DropdownOption).where(DropdownOption.id == option_id, DropdownOption.field_definition_id == field_id).with_for_update())
        if not option:
            raise FieldConfigurationError("Option not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            old = getattr(option, key)
            if old != value:
                setattr(option, key, value); _audit(db, option, "UPDATE", key, old, value)
    db.refresh(option)
    return option


def apply_custom_field_values(db: Session, product_id: int, values: dict, *, creating: bool = False) -> None:
    fields = list(db.scalars(select(FieldDefinition).options(selectinload(FieldDefinition.options)).where(FieldDefinition.system_field.is_(False), FieldDefinition.enabled.is_(True))))
    known = {field.field_key: field for field in fields}
    unknown = set(values) - set(known)
    if unknown:
        raise FieldConfigurationError(f"Unknown or disabled custom fields: {', '.join(sorted(unknown))}")
    for field in fields:
        supplied = field.field_key in values
        value = _normalize(values.get(field.field_key)) if supplied else None
        if field.required and value is None:
            raise FieldConfigurationError(f"{field.display_name} is required")
        if not supplied:
            continue
        typed = _typed_value(field, value)
        existing = db.scalar(select(CustomFieldValue).where(CustomFieldValue.ammo_product_id == product_id, CustomFieldValue.field_definition_id == field.id))
        if existing is None and value is None:
            continue
        if existing is None:
            existing = CustomFieldValue(ammo_product_id=product_id, field_definition_id=field.id); db.add(existing)
        existing.text_value = typed.get("text")
        existing.number_value = typed.get("number")
        existing.boolean_value = typed.get("boolean")


def validate_required_fields(db: Session, product) -> None:
    """Apply current required rules on create or the next metadata edit."""
    required = list(db.scalars(select(FieldDefinition).where(FieldDefinition.enabled.is_(True), FieldDefinition.required.is_(True))))
    custom_values = {
        value.field_definition_id: value
        for value in db.scalars(select(CustomFieldValue).where(CustomFieldValue.ammo_product_id == product.id))
    }
    for field in required:
        if field.system_field:
            if field.field_key == "upc":
                valid = db.scalar(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.ammo_product_id == product.id, AmmoPackageIdentifier.active.is_(True)).limit(1)) is not None
            elif field.field_key == "rounds_per_package":
                valid = db.scalar(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.ammo_product_id == product.id, AmmoPackageIdentifier.active.is_(True), AmmoPackageIdentifier.rounds_per_package.is_not(None)).limit(1)) is not None
            elif field.field_key == "storage_location":
                valid = product.storage_location_id is not None
            else:
                valid = getattr(product, field.field_key, None) is not None
            if not valid:
                raise FieldConfigurationError(f"{field.display_name} is required")
            continue
        value = custom_values.get(field.id)
        if not value or (value.text_value is None and value.number_value is None and value.boolean_value is None):
            raise FieldConfigurationError(f"{field.display_name} is required")


def _typed_value(field: FieldDefinition, value):
    if value is None:
        return {}
    if field.value_type == FieldValueType.TEXT:
        if not isinstance(value, str):
            raise FieldConfigurationError(f"{field.display_name} must be text")
        if field.field_type == FieldControlType.DROPDOWN:
            option = next((item for item in field.options if item.stable_key == value), None)
            if not option or not option.enabled:
                raise FieldConfigurationError(f"{field.display_name} has an invalid or retired option")
        return {"text": value}
    if field.value_type == FieldValueType.NUMBER:
        try:
            return {"number": Decimal(str(value))}
        except (InvalidOperation, ValueError):
            raise FieldConfigurationError(f"{field.display_name} must be numeric")
    if field.value_type == FieldValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise FieldConfigurationError(f"{field.display_name} must be true or false")
        return {"boolean": value}
    raise FieldConfigurationError("Unsupported field value type")


def _normalize(value):
    return None if isinstance(value, str) and not value.strip() else value


def _field(db: Session, field_id: int):
    field = db.scalar(select(FieldDefinition).options(selectinload(FieldDefinition.options)).where(FieldDefinition.id == field_id).with_for_update())
    if not field:
        raise FieldConfigurationError("Field not found")
    return field


def _has_values(db: Session, field_id: int) -> bool:
    return db.scalar(select(CustomFieldValue.id).where(CustomFieldValue.field_definition_id == field_id).limit(1)) is not None


def _audit(db: Session, entity, action: str, field_key, old, new):
    db.add(AuditEvent(entity_type=entity.__class__.__name__, entity_id=entity.id, action=action, field_key=field_key, old_value=_json(old), new_value=_json(new), source_type="browser"))


def _json(value):
    return None if value is None else json.dumps(value, default=str, sort_keys=True)
