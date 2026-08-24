import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InventoryViewPreference(Base):
    """Persisted inventory table configuration (spec §8). V1 only needs the
    single default view; the shape allows future named saved views (§24.20)."""

    __tablename__ = "inventory_view_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="Default")
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    visible_columns: Mapped[list] = mapped_column(JSON, default=list)
    column_order: Mapped[list] = mapped_column(JSON, default=list)
    sort_field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_direction: Mapped[str] = mapped_column(String(4), default="asc")
    page_size: Mapped[int] = mapped_column(Integer, default=50)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
