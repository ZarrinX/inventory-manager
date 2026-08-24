from pydantic import BaseModel, ConfigDict, Field


class InventoryViewPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    visible_columns: list[str]
    column_order: list[str]
    sort_field: str | None = None
    sort_direction: str
    page_size: int


class InventoryViewPreferenceUpdate(BaseModel):
    visible_columns: list[str] = Field(default_factory=list)
    column_order: list[str] = Field(default_factory=list)
    sort_field: str | None = None
    sort_direction: str = "asc"
    page_size: int = Field(default=50, ge=10, le=100)
