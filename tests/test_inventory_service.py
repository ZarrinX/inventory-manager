import pytest

from app.models import (
    AmmoPackageIdentifier, AmmoProduct, FieldControlType, FieldDefinition,
    FieldValueType, InventoryTransaction, TransactionType,
)
from app.schemas import InventoryTransactionCreate, TransactionReverseRequest
from app.services import inventory_service, metadata_service
from app.services.errors import NegativeInventoryError


def product(db, boxes=2, rounds_per_package=50):
    item = AmmoProduct(manufacturer="Federal", cartridge="9mm", box_quantity=boxes, round_quantity=boxes * rounds_per_package)
    db.add(item); db.flush()
    db.add(AmmoPackageIdentifier(ammo_product_id=item.id, upc="012345678905", rounds_per_package=rounds_per_package))
    db.commit()
    return item


def test_receive_remove_and_adjust_balances(db):
    item = product(db)
    product_id = item.id
    received = inventory_service.submit_transaction(db, InventoryTransactionCreate(transaction_type=TransactionType.RECEIVE, ammo_product_id=product_id, box_delta=3))
    assert received.transaction.new_box_balance == 5
    assert received.transaction.round_delta == 150
    db.rollback()
    removed = inventory_service.submit_transaction(db, InventoryTransactionCreate(transaction_type=TransactionType.REMOVE, ammo_product_id=product_id, box_delta=2))
    assert removed.transaction.box_delta == -2
    assert removed.transaction.new_round_balance == 150
    db.rollback()
    adjusted = inventory_service.submit_transaction(db, InventoryTransactionCreate(transaction_type=TransactionType.ADJUST, ammo_product_id=product_id, box_delta=-1))
    assert adjusted.transaction.new_box_balance == 2


def test_negative_inventory_is_rejected(db):
    item = product(db, boxes=1)
    with pytest.raises(NegativeInventoryError):
        inventory_service.submit_transaction(db, InventoryTransactionCreate(transaction_type=TransactionType.REMOVE, ammo_product_id=item.id, box_delta=2))


def test_idempotency_returns_original_transaction(db):
    item = product(db)
    payload = InventoryTransactionCreate(transaction_type=TransactionType.RECEIVE, ammo_product_id=item.id, box_delta=1, client_request_id="request-1")
    first = inventory_service.submit_transaction(db, payload)
    db.rollback()
    second = inventory_service.submit_transaction(db, payload)
    assert second.idempotent is True
    assert second.transaction.id == first.transaction.id
    assert db.query(InventoryTransaction).count() == 1


def test_reversal_creates_compensating_transaction(db):
    item = product(db)
    created = inventory_service.submit_transaction(db, InventoryTransactionCreate(transaction_type=TransactionType.RECEIVE, ammo_product_id=item.id, box_delta=1))
    transaction_id = created.transaction.id
    db.rollback()
    reversal = inventory_service.reverse_transaction(db, transaction_id, TransactionReverseRequest())
    assert reversal.transaction.reverses_transaction_id == transaction_id
    assert reversal.transaction.box_delta == -1


def test_new_product_satisfies_seeded_required_upc_field(db):
    db.add(FieldDefinition(
        field_key="upc", display_name="UPC", field_type=FieldControlType.TEXT,
        value_type=FieldValueType.TEXT, required=True, system_field=True,
    ))
    db.commit()

    result = inventory_service.submit_transaction(db, InventoryTransactionCreate(
        transaction_type=TransactionType.RECEIVE,
        new_product={
            "upc": "seeded-required-upc", "manufacturer": "Federal",
            "cartridge": "9mm", "rounds_per_package": 50,
            "initial_box_quantity": 1,
        },
    ))
    assert result.product.box_quantity == 1


def test_deleting_a_product_releases_its_upc_for_a_new_record(db):
    item = product(db)
    product_id = item.id
    metadata_service.soft_delete_product(db, product_id)
    db.rollback()

    recreated = inventory_service.submit_transaction(db, InventoryTransactionCreate(
        transaction_type=TransactionType.RECEIVE,
        new_product={
            "upc": "012345678905", "manufacturer": "New Federal",
            "cartridge": "9mm", "rounds_per_package": 50,
            "initial_box_quantity": 1,
        },
    ))
    assert recreated.product.id != product_id
