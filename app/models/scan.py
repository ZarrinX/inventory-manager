import datetime
import enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.db import Base


class ScanStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    RESOLVED = "RESOLVED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


class ScanEvent(Base):
    """Records that a barcode payload was received. A scan event never
    mutates inventory by itself — only a confirmed InventoryTransaction does
    that (spec §3.1, §24.4)."""

    __tablename__ = "scan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(String(255), index=True)
    barcode_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ammo_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("ammo_products.id"), nullable=True
    )
    scanner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ScanStatus] = mapped_column(
        SAEnum(ScanStatus, name="scan_status"), default=ScanStatus.RECEIVED
    )

    scanned_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["AmmoProduct | None"] = relationship()
