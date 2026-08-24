from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import AmmoPackageIdentifier, AmmoProduct, CustomFieldValue, FieldDefinition, FieldValueType, InventoryTransaction
from app.schemas import (
    AmmoPackageIdentifierOut,
    AmmoPackageIdentifierUpdate,
    AmmoProductOut,
    AmmoProductDetail,
    AmmoProductUpdate,
    CustomFieldValuesUpdate,
    InventoryPage,
    InventoryTransactionOut,
)
from app.services import field_service, identifier_service, metadata_service
from app.services.errors import DuplicateUpcError, ProductNotFoundError

router = APIRouter(prefix="/api/ammo", tags=["ammo"])


def _with_identifiers(query):
    return query.options(selectinload(AmmoProduct.identifiers))


@router.get("", response_model=InventoryPage)
def list_products(
    search: str | None = None,
    sort: str = "manufacturer",
    direction: str = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=100),
    low_stock: bool = False,
    custom_field: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    """Server-side inventory search, sorting, and pagination."""
    query = select(AmmoProduct).where(AmmoProduct.deleted_at.is_(None))
    if search:
        pattern = f"%{search.strip()}%"
        searchable = set(db.scalars(select(FieldDefinition.field_key).where(FieldDefinition.searchable.is_(True))))
        predicates = []
        column_map = {
            "manufacturer": AmmoProduct.manufacturer, "product_line": AmmoProduct.product_line,
            "manufacturer_sku": AmmoProduct.manufacturer_sku, "cartridge": AmmoProduct.cartridge,
            "bullet_type": AmmoProduct.bullet_type, "description": AmmoProduct.description,
            "notes": AmmoProduct.notes,
        }
        for key, column in column_map.items():
            if key in searchable:
                predicates.append(column.ilike(pattern))
        if "upc" in searchable:
            predicates.append(exists(select(AmmoPackageIdentifier.id).where(AmmoPackageIdentifier.ammo_product_id == AmmoProduct.id, AmmoPackageIdentifier.upc.ilike(pattern))))
        if "bullet_weight_gr" in searchable:
            try:
                predicates.append(AmmoProduct.bullet_weight_gr == Decimal(search.strip()))
            except InvalidOperation:
                pass
        if predicates:
            query = query.where(or_(*predicates))
    if low_stock:
        query = query.where(or_(
            (AmmoProduct.low_stock_threshold_unit == "boxes") & (AmmoProduct.box_quantity <= AmmoProduct.low_stock_threshold),
            (AmmoProduct.low_stock_threshold_unit == "rounds") & (AmmoProduct.round_quantity <= AmmoProduct.low_stock_threshold),
        ))
    for filter_value in custom_field:
        if ":" not in filter_value:
            raise HTTPException(status_code=422, detail="custom_field filters must be field_key:value")
        field_key, expected = filter_value.split(":", 1)
        field = db.scalar(select(FieldDefinition).where(FieldDefinition.field_key == field_key, FieldDefinition.system_field.is_(False)))
        if not field:
            raise HTTPException(status_code=422, detail=f"Unknown custom field: {field_key}")
        value_column = {
            FieldValueType.TEXT: CustomFieldValue.text_value,
            FieldValueType.NUMBER: CustomFieldValue.number_value,
            FieldValueType.BOOLEAN: CustomFieldValue.boolean_value,
        }[field.value_type]
        try:
            if field.value_type == FieldValueType.NUMBER:
                expected_value = Decimal(expected)
            elif field.value_type == FieldValueType.BOOLEAN:
                if expected.lower() not in {"true", "false"}:
                    raise ValueError
                expected_value = expected.lower() == "true"
            else:
                expected_value = expected
        except InvalidOperation as exc:
            raise HTTPException(status_code=422, detail=f"Invalid value for {field_key}") from exc
        query = query.where(exists(select(CustomFieldValue.id).where(CustomFieldValue.ammo_product_id == AmmoProduct.id, CustomFieldValue.field_definition_id == field.id, value_column == expected_value)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    sortable = {
        "manufacturer": AmmoProduct.manufacturer, "product_line": AmmoProduct.product_line,
        "cartridge": AmmoProduct.cartridge, "bullet_weight_gr": AmmoProduct.bullet_weight_gr,
        "bullet_type": AmmoProduct.bullet_type, "box_quantity": AmmoProduct.box_quantity,
        "round_quantity": AmmoProduct.round_quantity,
    }
    if sort.startswith("custom:"):
        field = db.scalar(select(FieldDefinition).where(FieldDefinition.field_key == sort.removeprefix("custom:"), FieldDefinition.system_field.is_(False)))
        if not field:
            raise HTTPException(status_code=422, detail="Unknown custom sort field")
        value_column = {FieldValueType.TEXT: CustomFieldValue.text_value, FieldValueType.NUMBER: CustomFieldValue.number_value, FieldValueType.BOOLEAN: CustomFieldValue.boolean_value}[field.value_type]
        column = select(value_column).where(CustomFieldValue.ammo_product_id == AmmoProduct.id, CustomFieldValue.field_definition_id == field.id).scalar_subquery()
    else:
        column = sortable.get(sort, AmmoProduct.manufacturer)
    ordering = column.desc() if direction.lower() == "desc" else column.asc()
    rows = list(db.scalars(_with_identifiers(query.order_by(ordering, AmmoProduct.id).offset((page - 1) * page_size).limit(page_size))))
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/by-upc/{upc}", response_model=AmmoProductOut)
def get_product_by_upc(upc: str, db: Session = Depends(get_db)) -> AmmoProduct:
    product = identifier_service.resolve_upc(db, upc)
    if not product:
        raise HTTPException(status_code=404, detail="No product found for this UPC")
    return product


@router.get("/{product_id}", response_model=AmmoProductDetail)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.scalar(_with_identifiers(select(AmmoProduct).where(AmmoProduct.id == product_id, AmmoProduct.deleted_at.is_(None))))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    transactions = list(db.scalars(select(InventoryTransaction).where(InventoryTransaction.ammo_product_id == product_id).order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())))
    return {**AmmoProductOut.model_validate(product).model_dump(), "transactions": [InventoryTransactionOut.model_validate(item).model_dump() for item in transactions]}


@router.patch("/{product_id}", response_model=AmmoProductOut)
def update_product(product_id: int, payload: AmmoProductUpdate, db: Session = Depends(get_db)) -> AmmoProduct:
    try:
        return metadata_service.update_product(db, product_id, payload)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{product_id}/custom-fields", response_model=AmmoProductOut)
def update_custom_fields(product_id: int, payload: CustomFieldValuesUpdate, db: Session = Depends(get_db)):
    try:
        with db.begin():
            product = db.scalar(_with_identifiers(select(AmmoProduct).where(AmmoProduct.id == product_id, AmmoProduct.deleted_at.is_(None))))
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            field_service.apply_custom_field_values(db, product.id, payload.values)
            field_service.validate_required_fields(db, product)
        db.refresh(product)
        return product
    except field_service.FieldConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{product_id}/identifiers/{identifier_id}", response_model=AmmoPackageIdentifierOut)
def update_identifier(product_id: int, identifier_id: int, payload: AmmoPackageIdentifierUpdate, db: Session = Depends(get_db)):
    try:
        return metadata_service.update_identifier(db, product_id, identifier_id, payload)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateUpcError as exc:
        raise HTTPException(status_code=409, detail="UPC already exists") from exc
    except metadata_service.MetadataConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{product_id}", response_model=AmmoProductOut)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> AmmoProduct:
    try:
        return metadata_service.soft_delete_product(db, product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{product_id}/restore", response_model=AmmoProductOut)
def restore_product(product_id: int, db: Session = Depends(get_db)) -> AmmoProduct:
    try:
        return metadata_service.restore_product(db, product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except metadata_service.MetadataConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
