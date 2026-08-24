from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    DropdownOptionCreate, DropdownOptionOut, DropdownOptionUpdate,
    FieldDefinitionCreate, FieldDefinitionOut, FieldDefinitionUpdate,
)
from app.services import field_service

router = APIRouter(prefix="/api/admin/fields", tags=["admin fields"])


def _error(exc: field_service.FieldConfigurationError):
    raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[FieldDefinitionOut])
def list_fields(db: Session = Depends(get_db)):
    return field_service.list_fields(db)


@router.post("", response_model=FieldDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: FieldDefinitionCreate, db: Session = Depends(get_db)):
    try:
        return field_service.create_field(db, payload)
    except field_service.FieldConfigurationError as exc:
        _error(exc)


@router.patch("/{field_id}", response_model=FieldDefinitionOut)
def update_field(field_id: int, payload: FieldDefinitionUpdate, db: Session = Depends(get_db)):
    try:
        return field_service.update_field(db, field_id, payload)
    except field_service.FieldConfigurationError as exc:
        _error(exc)


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(field_id: int, db: Session = Depends(get_db)):
    try:
        field_service.delete_field(db, field_id)
    except field_service.FieldConfigurationError as exc:
        _error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{field_id}/options", response_model=DropdownOptionOut, status_code=status.HTTP_201_CREATED)
def create_option(field_id: int, payload: DropdownOptionCreate, db: Session = Depends(get_db)):
    try:
        return field_service.create_option(db, field_id, payload)
    except field_service.FieldConfigurationError as exc:
        _error(exc)


@router.patch("/{field_id}/options/{option_id}", response_model=DropdownOptionOut)
def update_option(field_id: int, option_id: int, payload: DropdownOptionUpdate, db: Session = Depends(get_db)):
    try:
        return field_service.update_option(db, field_id, option_id, payload)
    except field_service.FieldConfigurationError as exc:
        _error(exc)
