import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AmmoPackageIdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    upc: str
    rounds_per_package: int
    package_description: str | None = None
    active: bool


class AmmoProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    manufacturer: str
    product_line: str | None = None
    manufacturer_sku: str | None = None
    cartridge: str
    bullet_weight_gr: Decimal | None = None
    bullet_type: str | None = None
    description: str | None = None
    notes: str | None = None
    low_stock_threshold: Decimal | None = None
    low_stock_threshold_unit: str | None = None
    box_quantity: int
    round_quantity: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    identifiers: list[AmmoPackageIdentifierOut] = []


class AmmoProductCreate(BaseModel):
    """Minimal unknown-UPC creation payload (spec §5.2). Field-definition
    driven custom fields and full validation land in a later phase."""

    upc: str
    manufacturer: str
    product_line: str | None = None
    manufacturer_sku: str | None = None
    cartridge: str
    bullet_weight_gr: Decimal | None = None
    bullet_type: str | None = None
    rounds_per_package: int
    description: str | None = None
    notes: str | None = None
    storage_location_id: int | None = None
    initial_box_quantity: int = 0
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AmmoProductUpdate(BaseModel):
    manufacturer: str | None = None
    product_line: str | None = None
    manufacturer_sku: str | None = None
    cartridge: str | None = None
    bullet_weight_gr: Decimal | None = None
    bullet_type: str | None = None
    description: str | None = None
    notes: str | None = None
    storage_location_id: int | None = None
    low_stock_threshold: Decimal | None = None
    low_stock_threshold_unit: str | None = None

    @model_validator(mode="after")
    def preserve_required_fields(self):
        for field in ("manufacturer", "cartridge"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AmmoPackageIdentifierUpdate(BaseModel):
    upc: str | None = None
    rounds_per_package: int | None = Field(default=None, ge=1)
    package_description: str | None = None
    active: bool | None = None
    confirm_rounds_per_package_change: bool = False


class InventoryPage(BaseModel):
    items: list[AmmoProductOut]
    total: int
    page: int
    page_size: int


class AmmoProductDetail(AmmoProductOut):
    transactions: list["InventoryTransactionOut"]
    custom_fields: dict[str, Any] = Field(default_factory=dict)
