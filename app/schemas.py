import datetime

from pydantic import BaseModel, ConfigDict


class ItemBase(BaseModel):
    upc: str
    name: str
    description: str | None = None
    quantity: int = 0


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    quantity: int | None = None


class ItemAdjust(BaseModel):
    delta: int


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ScanResult(BaseModel):
    upc: str
    scanned_at: datetime.datetime
    item: ItemOut | None = None
