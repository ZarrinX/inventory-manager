import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
    initial_box_quantity: int = 0
