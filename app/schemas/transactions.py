import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import TransactionType
from app.schemas.ammo import AmmoProductCreate
from app.schemas.ammo import AmmoProductOut


class InventoryTransactionCreate(BaseModel):
    """The single command for all confirmed inventory mutations."""

    transaction_type: TransactionType
    box_delta: int | None = None
    ammo_product_id: int | None = None
    scan_event_id: int | None = None
    upc: str | None = None
    new_product: AmmoProductCreate | None = None
    notes: str | None = None
    client_request_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_target(self):
        if self.new_product:
            if self.transaction_type != TransactionType.RECEIVE:
                raise ValueError("A new product must use a RECEIVE transaction")
            if self.ammo_product_id or self.upc:
                raise ValueError("new_product cannot be combined with an existing product target")
            if self.scan_event_id is not None and self.scan_event_id < 1:
                raise ValueError("scan_event_id must be positive")
            return self
        if not (self.ammo_product_id or self.scan_event_id or self.upc):
            raise ValueError("Provide ammo_product_id, scan_event_id, or upc")
        if self.box_delta is None or self.box_delta == 0:
            raise ValueError("box_delta must be non-zero for an existing product")
        return self


class TransactionReverseRequest(BaseModel):
    notes: str | None = None
    client_request_id: str | None = Field(default=None, max_length=64)


class InventoryTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ammo_product_id: int
    transaction_type: TransactionType
    box_delta: int
    round_delta: int
    previous_box_balance: int
    new_box_balance: int
    previous_round_balance: int
    new_round_balance: int
    notes: str | None = None
    created_at: datetime.datetime


class TransactionSubmissionOut(BaseModel):
    transaction: InventoryTransactionOut
    product: AmmoProductOut
    idempotent: bool = False


class TransactionHistoryItem(InventoryTransactionOut):
    manufacturer: str
    product_line: str | None = None
    cartridge: str
    source_type: str | None = None
    source_id: str | None = None
    reverses_transaction_id: int | None = None
    is_reversed: bool = False


class TransactionHistoryPage(BaseModel):
    items: list[TransactionHistoryItem]
    total: int
    page: int
    page_size: int
