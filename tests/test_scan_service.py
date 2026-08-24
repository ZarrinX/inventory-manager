import time

from app.models import ScanStatus
from app.services.scan_service import ScanDisposition, ScanWorkflow


def test_fifo_queue_cancel_and_promote(db):
    workflow = ScanWorkflow()
    first = workflow.record(db, "111")
    second = workflow.record(db, "222")
    third = workflow.record(db, "333")
    assert first.disposition == ScanDisposition.ACTIVE
    assert second.disposition == ScanDisposition.QUEUED
    assert third.queue_depth == 2
    next_result = workflow.finish(db, first.event.id, ScanStatus.CANCELED)
    assert next_result.finished_event.status == ScanStatus.CANCELED
    assert next_result.next_scan.event.payload == "222"
    assert next_result.next_scan.event.status == ScanStatus.RESOLVED


def test_debounce_and_queue_overflow(db):
    workflow = ScanWorkflow()
    assert workflow.record(db, "111").disposition == ScanDisposition.ACTIVE
    assert workflow.record(db, "111").disposition == ScanDisposition.DUPLICATE
    for code in ("222", "333", "444", "555", "666"):
        assert workflow.record(db, code).disposition == ScanDisposition.QUEUED
    assert workflow.record(db, "777").disposition == ScanDisposition.OVERFLOW
