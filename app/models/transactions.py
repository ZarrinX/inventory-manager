import datetime
import enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.db import Base


class TransactionType(str, enum.Enum):
    RECEIVE = "RECEIVE"
    REMOVE = "REMOVE"
    ADJUST = "ADJUST"


class InventoryTransaction(Base):
    """An immutable, confirmed inventory change (spec §6.2). Corrections are
    made by creating new ADJUST or reversal transactions — history is never
    edited or deleted."""

    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ammo_product_id: Mapped[int] = mapped_column(ForeignKey("ammo_products.id"), index=True)
    scan_event_id: Mapped[int | None] = mapped_column(ForeignKey("scan_events.id"), nullable=True)

    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type")
    )
    box_delta: Mapped[int] = mapped_column(Integer)
    round_delta: Mapped[int] = mapped_column(Integer)
    previous_box_balance: Mapped[int] = mapped_column(Integer)
    new_box_balance: Mapped[int] = mapped_column(Integer)
    previous_round_balance: Mapped[int] = mapped_column(Integer)
    new_round_balance: Mapped[int] = mapped_column(Integer)

    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    # Structured source tracking instead of a free-text string (spec §24.10).
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Client-supplied idempotency key; repeated submissions with the same key
    # must not create a second transaction (spec §24.9).
    client_request_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    reverses_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_transactions.id"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["AmmoProduct"] = relationship()
    scan_event: Mapped["ScanEvent | None"] = relationship()
    reverses: Mapped["InventoryTransaction | None"] = relationship(remote_side=[id])
