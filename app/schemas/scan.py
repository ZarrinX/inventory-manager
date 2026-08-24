import datetime

from pydantic import BaseModel

from app.schemas.ammo import AmmoProductOut


class ScanResult(BaseModel):
    upc: str
    scanned_at: datetime.datetime
    product: AmmoProductOut | None = None
