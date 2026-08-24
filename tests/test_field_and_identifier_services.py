import pytest

from app.models import (
    AmmoPackageIdentifier,
    AmmoProduct,
    DropdownOption,
    FieldControlType,
    FieldDefinition,
    FieldValueType,
)
from app.services import field_service, identifier_service


def product(db):
    item = AmmoProduct(manufacturer="Federal", cartridge="9mm")
    db.add(item)
    db.flush()
    return item


def test_multiple_active_identifiers_resolve_to_one_product(db):
    item = product(db)
    db.add_all([
        AmmoPackageIdentifier(ammo_product_id=item.id, upc="111", rounds_per_package=50),
        AmmoPackageIdentifier(ammo_product_id=item.id, upc="222", rounds_per_package=100),
    ])
    db.commit()

    assert identifier_service.resolve_upc(db, "111").id == item.id
    resolved = identifier_service.resolve_upc(db, "222")
    assert resolved.id == item.id
    assert {identifier.upc for identifier in resolved.identifiers} == {"111", "222"}


def test_required_numeric_and_retired_dropdown_custom_fields_are_validated(db):
    item = product(db)
    number = FieldDefinition(
        field_key="velocity", display_name="Velocity", field_type=FieldControlType.TEXT,
        value_type=FieldValueType.NUMBER, required=True,
    )
    dropdown = FieldDefinition(
        field_key="purpose", display_name="Purpose", field_type=FieldControlType.DROPDOWN,
        value_type=FieldValueType.TEXT,
    )
    db.add_all([number, dropdown])
    db.flush()
    db.add_all([
        DropdownOption(field_definition_id=dropdown.id, stable_key="range", label="Range"),
        DropdownOption(field_definition_id=dropdown.id, stable_key="retired", label="Retired", enabled=False),
    ])
    db.commit()

    with pytest.raises(field_service.FieldConfigurationError, match="Velocity is required"):
        field_service.apply_custom_field_values(db, item.id, {"purpose": "range"})
    db.rollback()
    with pytest.raises(field_service.FieldConfigurationError, match="Velocity must be numeric"):
        field_service.apply_custom_field_values(db, item.id, {"velocity": "fast"})
    db.rollback()
    with pytest.raises(field_service.FieldConfigurationError, match="invalid or retired option"):
        field_service.apply_custom_field_values(db, item.id, {"velocity": 1200, "purpose": "retired"})
    db.rollback()

    field_service.apply_custom_field_values(db, item.id, {"velocity": "1200", "purpose": "range"})
    db.commit()
