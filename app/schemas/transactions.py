import datetime

from pydantic import BaseModel, ConfigDict

from app.models import TransactionType


class InventoryTransactionCreate(BaseModel):
    transaction_type: TransactionType
    box_delta: int
    notes: str | None = None


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
