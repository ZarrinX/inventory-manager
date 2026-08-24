import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    action: str
    field_key: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    created_at: datetime.datetime
