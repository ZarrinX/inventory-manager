import datetime
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.db import Base


class FieldControlType(str, enum.Enum):
    """How the field is presented/edited."""

    TEXT = "text"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"


class FieldValueType(str, enum.Enum):
    """The underlying type of the stored value."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"


class FieldDefinition(Base):
    """Describes a system or custom ammunition field. Renaming `display_name`
    must never change `field_key`, so stored values/relationships stay
    stable (spec §9.1)."""

    __tablename__ = "field_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    field_type: Mapped[FieldControlType] = mapped_column(
        SAEnum(FieldControlType, name="field_control_type")
    )
    value_type: Mapped[FieldValueType] = mapped_column(
        SAEnum(FieldValueType, name="field_value_type")
    )
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # True for the built-in fields listed in spec §5.2 (UPC, Manufacturer, ...).
    system_field: Mapped[bool] = mapped_column(Boolean, default=False)
    # Type-specific config (e.g. decimal precision); shape depends on field_type.
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    options: Mapped[list["DropdownOption"]] = relationship(
        back_populates="field_definition", cascade="all, delete-orphan"
    )


class CustomFieldValue(Base):
    """Typed value storage for a custom field on a specific AmmoProduct. Only
    the column matching the field's `value_type` should be populated
    (spec §10.2-10.4)."""

    __tablename__ = "custom_field_values"
    __table_args__ = (
        UniqueConstraint(
            "ammo_product_id", "field_definition_id", name="uq_custom_field_value_product_field"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ammo_product_id: Mapped[int] = mapped_column(ForeignKey("ammo_products.id"), index=True)
    field_definition_id: Mapped[int] = mapped_column(
        ForeignKey("field_definitions.id"), index=True
    )

    text_value: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    field_definition: Mapped["FieldDefinition"] = relationship()


class DropdownOption(Base):
    """An option for a dropdown-type FieldDefinition. Retired (disabled)
    options remain valid on existing records but can't be selected for new
    values (spec §24.15)."""

    __tablename__ = "dropdown_options"
    __table_args__ = (
        UniqueConstraint(
            "field_definition_id", "stable_key", name="uq_dropdown_option_field_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(
        ForeignKey("field_definitions.id"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    field_definition: Mapped["FieldDefinition"] = relationship(back_populates="options")
