from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import FieldControlType, FieldValueType


class DropdownOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stable_key: str
    label: str
    sort_order: int
    unit: str | None = None
    enabled: bool


class FieldDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_key: str
    display_name: str
    field_type: FieldControlType
    value_type: FieldValueType
    required: bool
    enabled: bool
    searchable: bool
    sort_order: int
    system_field: bool
    configuration: dict | None = None
    options: list[DropdownOptionOut] = []


class FieldDefinitionCreate(BaseModel):
    field_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    field_type: FieldControlType
    value_type: FieldValueType
    required: bool = False
    enabled: bool = True
    searchable: bool = False
    sort_order: int = 100
    unit: str | None = Field(default=None, max_length=32)
    configuration: dict | None = None

    @model_validator(mode="after")
    def validate_control_and_value(self):
        if self.field_type == FieldControlType.CHECKBOX and self.value_type != FieldValueType.BOOLEAN:
            raise ValueError("Checkbox fields must use boolean values")
        if self.field_type == FieldControlType.DROPDOWN and self.value_type != FieldValueType.TEXT:
            raise ValueError("Dropdown fields store stable text keys")
        return self


class FieldDefinitionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    field_type: FieldControlType | None = None
    value_type: FieldValueType | None = None
    required: bool | None = None
    enabled: bool | None = None
    searchable: bool | None = None
    sort_order: int | None = None
    unit: str | None = Field(default=None, max_length=32)
    configuration: dict | None = None


class DropdownOptionCreate(BaseModel):
    stable_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=128)
    sort_order: int = 0


class DropdownOptionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    sort_order: int | None = None
    enabled: bool | None = None


class CustomFieldValuesUpdate(BaseModel):
    values: dict[str, Any]
