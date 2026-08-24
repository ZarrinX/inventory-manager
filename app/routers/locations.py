from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Location
from app.schemas import LocationCreate, LocationOut, LocationUpdate

router = APIRouter(prefix="/api/locations", tags=["locations"])


def _location(db: Session, location_id: int) -> Location:
    location = db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def _validate_parent(db: Session, location_id: int | None, parent_id: int | None) -> None:
    if parent_id is None:
        return
    if location_id == parent_id:
        raise HTTPException(status_code=422, detail="A location cannot be its own parent")
    current = parent_id
    while current is not None:
        if current == location_id:
            raise HTTPException(status_code=422, detail="Location hierarchy cannot contain a cycle")
        current = db.scalar(select(Location.parent_id).where(Location.id == current))
        if current is None and db.scalar(select(Location.id).where(Location.id == parent_id)) is None:
            raise HTTPException(status_code=422, detail="Parent location not found")


@router.get("", response_model=list[LocationOut])
def list_locations(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = select(Location).order_by(Location.name, Location.id)
    if not include_inactive:
        query = query.where(Location.active.is_(True))
    return list(db.scalars(query))


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    with db.begin():
        _validate_parent(db, None, payload.parent_id)
        location = Location(**payload.model_dump())
        db.add(location)
    db.refresh(location)
    return location


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(location_id: int, payload: LocationUpdate, db: Session = Depends(get_db)):
    with db.begin():
        location = _location(db, location_id)
        changes = payload.model_dump(exclude_unset=True)
        if "parent_id" in changes:
            _validate_parent(db, location_id, changes["parent_id"])
        for key, value in changes.items():
            setattr(location, key, value)
    db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_location(location_id: int, db: Session = Depends(get_db)):
    with db.begin():
        _location(db, location_id).active = False
    return Response(status_code=status.HTTP_204_NO_CONTENT)
