from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.broadcast import manager, scan_payload
from app.db import get_db
from app.services import scan_service

router = APIRouter(prefix="/api/scans", tags=["scans"])


async def _finish_scan(scan_id: int, finish, db: Session):
    try:
        result = finish(db, scan_id)
    except scan_service.ScanTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result.next_scan:
        await manager.broadcast(scan_payload(result.next_scan))
    return {
        "scan_id": result.finished_event.id,
        "status": result.finished_event.status,
        "queue_depth": result.next_scan.queue_depth if result.next_scan else 0,
        "next_scan_id": result.next_scan.event.id if result.next_scan else None,
    }


@router.get("/active")
def get_active_scan(db: Session = Depends(get_db)):
    result = scan_service.active_scan(db)
    if not result:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return scan_payload(result)


@router.post("/{scan_id}/cancel")
async def cancel_scan(scan_id: int, db: Session = Depends(get_db)):
    """Cancel the active scan without changing inventory, then promote FIFO."""
    return await _finish_scan(scan_id, scan_service.cancel_scan, db)


@router.post("/{scan_id}/complete")
async def complete_scan(scan_id: int, db: Session = Depends(get_db)):
    """Mark an active scan complete after its transaction has succeeded."""
    return await _finish_scan(scan_id, scan_service.complete_scan, db)
