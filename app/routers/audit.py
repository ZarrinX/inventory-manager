from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEvent
from app.schemas import AuditEventOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    entity_type: str | None = None,
    entity_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditEvent.entity_id == entity_id)
    return list(db.scalars(query))
