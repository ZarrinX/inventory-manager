from pydantic import BaseModel, ConfigDict, Field


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: int | None = None
    active: bool


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None
    active: bool = True


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    active: bool | None = None
