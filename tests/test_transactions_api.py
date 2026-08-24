from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app


def test_transaction_api_creates_inventory_and_is_idempotent(db):
    def override_db():
        session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    payload = {
        "transaction_type": "RECEIVE",
        "client_request_id": "api-create-1",
        "new_product": {
            "upc": "098765432109",
            "manufacturer": "Federal",
            "cartridge": "9mm",
            "rounds_per_package": 50,
            "initial_box_quantity": 2,
        },
    }
    try:
        with TestClient(app) as client:
            first = client.post("/api/transactions", json=payload)
            assert first.status_code == 201
            body = first.json()
            assert body["transaction"]["new_box_balance"] == 2
            assert body["transaction"]["new_round_balance"] == 100

            repeated = client.post("/api/transactions", json=payload)
            assert repeated.status_code == 200
            assert repeated.json()["idempotent"] is True
            assert repeated.json()["transaction"]["id"] == body["transaction"]["id"]

            inventory = client.get("/api/ammo", params={"search": "Federal", "page_size": 10})
            assert inventory.status_code == 200
            assert inventory.json()["total"] == 1

            product_id = body["product"]["id"]
            duplicate = client.post("/api/transactions", json={
                **payload, "client_request_id": "api-create-2",
            })
            assert duplicate.status_code == 409
            assert client.patch(f"/api/ammo/{product_id}", json={"notes": "range stock"}).status_code == 200
            removed = client.post("/api/transactions", json={
                "transaction_type": "REMOVE", "ammo_product_id": product_id, "box_delta": 1,
            })
            assert removed.status_code == 201
            adjustment = client.post("/api/transactions", json={
                "transaction_type": "ADJUST", "ammo_product_id": product_id, "box_delta": 2,
            })
            assert adjustment.status_code == 201
            reversal = client.post(f"/api/transactions/{adjustment.json()['transaction']['id']}/reverse", json={})
            assert reversal.status_code == 201
            history = client.get("/api/transactions", params={"ammo_product_id": product_id})
            assert history.status_code == 200
            assert history.json()["total"] == 4

            created_field = client.post("/api/admin/fields", json={
                "field_key": "purpose", "display_name": "Purpose", "field_type": "dropdown",
                "value_type": "text", "unit": "category", "searchable": True,
            })
            assert created_field.status_code == 201
            assert created_field.json()["unit"] == "category"
            field_id = created_field.json()["id"]
            assert client.post(f"/api/admin/fields/{field_id}/options", json={"stable_key": "range", "label": "Range"}).status_code == 201
            assert client.patch(f"/api/admin/fields/{field_id}", json={"display_name": "Use"}).status_code == 200
            assert client.patch(f"/api/ammo/{product_id}/custom-fields", json={"values": {"purpose": "range"}}).status_code == 200
            filtered = client.get("/api/ammo", params={"custom_field": "purpose:range", "sort": "custom:purpose", "page_size": 10})
            assert filtered.status_code == 200
            assert filtered.json()["total"] == 1

            preference = client.put("/api/preferences/inventory-view", json={
                "visible_columns": ["manufacturer", "cartridge"], "column_order": ["cartridge", "manufacturer"],
                "sort_field": "cartridge", "sort_direction": "desc", "page_size": 25,
            })
            assert preference.status_code == 200
            assert client.get("/api/preferences/inventory-view").json()["sort_field"] == "cartridge"
    finally:
        app.dependency_overrides.clear()
