import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AmmoProduct(Base):
    """The underlying ammunition load, independent of any specific UPC/package
    size. Multiple `AmmoPackageIdentifier` rows (different UPCs) can resolve
    to the same product (spec §24.1)."""

    __tablename__ = "ammo_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manufacturer: Mapped[str] = mapped_column(String(255))
    product_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cartridge: Mapped[str] = mapped_column(String(128))
    bullet_weight_gr: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    bullet_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    storage_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )

    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # "boxes" | "rounds" (spec §24.12)
    low_stock_threshold_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Denormalized running balances, kept in sync transactionally whenever an
    # InventoryTransaction is created (see the future inventory service) so
    # reads never need to replay the full transaction history.
    box_quantity: Mapped[int] = mapped_column(Integer, default=0)
    round_quantity: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Soft delete: deleted_at IS NOT NULL means the product is retired (§24.3).
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    identifiers: Mapped[list["AmmoPackageIdentifier"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    storage_location: Mapped["Location | None"] = relationship()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AmmoPackageIdentifier(Base):
    """A specific UPC/package size that resolves to an `AmmoProduct`. Scanning
    any active identifier for a product opens the same inventory item, but
    the identifier's own `rounds_per_package` is used for that scan's
    transaction math (spec §24.1)."""

    __tablename__ = "ammo_package_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ammo_product_id: Mapped[int] = mapped_column(ForeignKey("ammo_products.id"), index=True)
    upc: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rounds_per_package: Mapped[int] = mapped_column(Integer)
    package_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[AmmoProduct] = relationship(back_populates="identifiers")
