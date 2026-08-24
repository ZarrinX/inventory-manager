# TODO — Inventory Manager V1

Derived from [spec.md](spec.md). Check items off as they're completed. Group
order roughly follows dependency order (migrations/data model first, since
almost everything else depends on the new schema), not the spec's section
order.

References like `(§24.5)` point back to the relevant spec section.

---

## Phase 0 — Migrations Foundation

> Deviation from the original plan below: since the PoC never held real
> production data (only manual smoke-test rows), the initial migration goes
> straight to the Phase 1 schema instead of first capturing the old
> `Item`/`ScanEvent` tables and migrating away from them in a second step.

- [x] Add Alembic to the project (`alembic/`, `alembic.ini`)
- [x] Generate an initial migration capturing the current `Item`/`ScanEvent`
      schema — combined with the Phase 1 schema instead (see note above);
      `alembic/versions/14736a9fea83_initial_schema.py`
- [x] Remove `Base.metadata.create_all()` from app startup; migrations become
      the schema-upgrade mechanism (§15)
- [x] Document `alembic upgrade head` in README/AGENTS.md dev + deploy steps
- [x] Add a Jenkinsfile stage to run `alembic upgrade head` on deploy (mirrors
      muthur-ui's migrate stage)

## Phase 1 — Data Model Refactor

Replace the current single `Item` table with the product/identifier split
required by §24.1.

- [x] `AmmoProduct` model (manufacturer, product_line, manufacturer_sku,
      cartridge, bullet_weight_gr, bullet_type, description, notes,
      storage_location, low_stock_threshold, low_stock_threshold_unit,
      created_at, updated_at, deleted_at)
- [x] `AmmoPackageIdentifier` model (ammo_product_id, upc, rounds_per_package,
      package_description, active, created_at, updated_at)
- [x] `InventoryTransaction` model (ammo_product_id, scan_event_id,
      transaction_type, box_delta, round_delta, previous/new box+round
      balances, location_id, source_type, source_id, client_request_id,
      reverses_transaction_id, notes, created_at) (§6.2, §24.9, §24.10)
- [x] Update `ScanEvent` model: payload, barcode_format, ammo_product_id
      (nullable), scanner_id (nullable), status (`RECEIVED`/`RESOLVED`/
      `COMPLETED`/`CANCELED`/`FAILED`), scanned_at (§24.4)
- [x] `FieldDefinition` model (field_key, display_name, field_type,
      value_type, required, enabled, searchable, sort_order, system_field,
      configuration, created_at, updated_at)
- [x] `CustomFieldValue` model (ammo_product_id, field_definition_id,
      text_value, number_value, boolean_value) — only one value column
      populated per row
- [x] `DropdownOption` model (field_definition_id, stable_key, label,
      sort_order, enabled)
- [x] `Location` model (name, parent_id, active) (§24.11)
- [x] `InventoryViewPreference` model (name, is_default, visible_columns,
      column_order, sort_field, sort_direction, page_size, created_at,
      updated_at) (§8, §24.20)
- [x] `AuditEvent` model (entity_type, entity_id, action, field_key,
      old_value, new_value, source_type, source_id, created_at) (§24.24)
- [x] Migration: seed default `FieldDefinition` rows for the system fields
      listed in §5.2
- [x] Migration/backfill plan for any existing local `Item`/`ScanEvent` data
      into the new schema (or explicitly accept a clean slate if no
      production data exists yet) — clean slate accepted, see Phase 0 note
- [x] Numeric custom-field storage uses `Numeric`/`Decimal`, not float (§10.2)

## Phase 2 — Service Layer

Introduce the service layer so routes and the scanner handler share one set
of business rules (§14, §22.5).

- [x] `app/services/` package: `identifier_service` (UPC → product
      resolution), `inventory_service` (balance calculations,
      transaction creation), `scan_service` (scan lifecycle, queue,
      debounce — queue/debounce itself still lands in Phase 3)
- [x] `app/repositories/` (or keep repository logic in services if the
      project stays small) for DB access used by both HTTP routes and the
      scanner callback — kept in services, project is small enough
- [x] Reorganize `app/models.py` → `app/models/` package if it grows large
      enough to warrant splitting (done in Phase 1)
- [x] Reorganize `app/schemas.py` → `app/schemas/` similarly

## Phase 3 — Scan Workflow

- [ ] Scan event creation never mutates inventory by itself (§3.1, §18)
- [ ] UPC resolution against `AmmoPackageIdentifier.upc` (active only)
- [ ] WebSocket scan event payload matches the contract in §13
      (`event`, `scan_id`, `code`, `format`, `timestamp`)
- [ ] Known-UPC scan → emits enough product detail for the IN/OUT modal
      (§5.3): manufacturer, product_line, cartridge, bullet_weight,
      bullet_type, rounds_per_box, UPC, current box/round balance
- [ ] Unknown-UPC scan → emits enough info for the New Ammunition modal
      (§5.2), UPC pre-filled/read-only
- [ ] FIFO scan queue, max depth 5, reject/log overflow beyond that (§24.5)
- [ ] Only one active/unresolved scan modal at a time; queued scans never
      replace it (§5.4)
- [ ] 500ms duplicate-scan debounce per (scanner/source, UPC) (§24.6)
- [ ] Cancel workflow: scan status set to `CANCELED`, no transaction created,
      scan remains in history (§24.4)
- [ ] Next queued scan is processed after the active modal is
      completed/canceled

## Phase 4 — Inventory Transactions

- [ ] `POST /api/transactions` is the only path that mutates inventory
      (§3.2, §12)
- [ ] Support `RECEIVE`/`IN`, `REMOVE`/`OUT`, `ADJUST` transaction types
- [ ] Unknown-UPC confirm: atomically create `AmmoProduct` +
      `AmmoPackageIdentifier` + initial `RECEIVE` transaction (§5.2)
- [ ] Known-UPC confirm: atomically create IN/OUT transaction using the
      scanned identifier's `rounds_per_package` (§24.1)
- [ ] Reject `OUT` operations that would produce negative balance (§6.2)
- [ ] Transactions are immutable — no update/delete endpoints (§6.2)
- [ ] Incorrect inventory corrected via new `ADJUST` transactions only
- [ ] Transaction reversal: `POST /api/transactions/{id}/reverse` creates a
      compensating transaction with `reverses_transaction_id`, validates
      against current inventory rules, never mutates the original (§24.8)
- [ ] Idempotency: accept `client_request_id` on all mutating transaction
      endpoints; duplicate submissions return the original result instead of
      creating a new transaction (§24.9)
- [ ] Historical transactions store their own resolved round delta /
      package-size snapshot rather than recalculating from the current
      identifier definition (§24.2)

## Phase 5 — Editing, Deletion, Audit

- [ ] `PATCH` endpoint(s) for editing `AmmoProduct`/`AmmoPackageIdentifier`
      metadata
- [ ] Every metadata edit writes an `AuditEvent` (entity, field, old/new
      value, timestamp, source) (§24.2, §24.24)
- [ ] Changing `rounds_per_package` on an identifier with existing
      transactions requires explicit confirmation; historical transactions
      keep their original values (§24.2)
- [ ] Soft-delete (`deleted_at`, `active=false`) for `AmmoProduct`; deleted
      records disappear from normal views but remain visible in history/audit
      (§24.3)
- [ ] Admin restore function for soft-deleted products
- [ ] Audit history API + admin UI view, filterable, immutable (§24.24)

## Phase 6 — Web UI: Core Navigation & Scan Modals

- [ ] Nav structure: Dashboard/Inventory, Transaction History, Admin,
      Scanner/System Status (§7.1)
- [ ] Unknown-UPC "New Ammunition" modal (fields from §5.2, driven by
      `FieldDefinition` config, required box quantity input)
- [ ] Known-UPC "Inventory Transaction" modal (identifying info + current
      balance + IN/OUT toggle + box quantity, default 1) (§5.3)
- [ ] Large touch-friendly IN/OUT controls (§5.3, §18)
- [ ] Pending-scan indicator / queue depth display (§24.5)
- [ ] Scanner-disconnected status indicator; inventory browsing/manual entry
      still available while disconnected (§24.25)
- [ ] WebSocket-disconnected indicator with auto-reconnect; no assumption
      that missed scans were processed (§24.25)
- [ ] Manual Entry button opening the same blank ammunition modal, no scan
      required (§24.7)

## Phase 7 — Web UI: Inventory Table

- [ ] Server-side search across all searchable configured fields (§7.2,
      §24.18 semantics per field type)
- [ ] Server-side sort across all sortable fields, asc/desc per column
      (§7.3, §24.19)
- [ ] Server-side pagination
- [ ] Inventory detail view: full record + associated transaction history
      (§7.4)
- [ ] Persistent default view: visible columns, column order, default sort
      field/direction, rows per page — saved server-side, restored on reopen
      (§8)
- [ ] "Reset to Default" action for the saved view (§24.20)
- [ ] Saved view gracefully ignores retired/deleted fields instead of
      failing (§24.20)
- [ ] Low-stock filter/indicator using `low_stock_threshold` +
      `low_stock_threshold_unit` (§24.12)

## Phase 8 — Web UI: Transaction History

- [ ] Global transaction history view with all columns from §7.5
- [ ] Global search across history
- [ ] Sort by sortable fields, newest-first default
- [ ] Filters: date range, transaction type, ammo/SKU, cartridge/caliber,
      manufacturer, source/client (§7.5)
- [ ] Reverse-transaction action available from the history view where valid
      (§24.8)

## Phase 9 — Admin: Field & Custom Field Management

- [ ] Field administration UI: display name, required/optional,
      enabled/disabled, display order, searchable (§9.1)
- [ ] Enforce required-field validation server-side; client-side validation
      as a UX nicety only (§9.2)
- [ ] Changing optional → required does not hide/break existing incomplete
      records; rules enforced only on next edit (§9.2)
- [ ] Critical system fields (UPC, rounds-per-package) marked
      non-deletable/permanently required where applicable (§9.3)
- [ ] Custom field CRUD: text/alphanumeric, number (decimal), boolean,
      dropdown (§10)
- [ ] Custom field creation requires no DB migration (typed value table)
- [ ] Custom fields with stored values are retired/disabled, not
      hard-deleted (§24.13)
- [ ] Custom fields with no stored values may be hard-deleted
- [ ] Field type changes on fields with existing values are blocked; document
      the create-new/migrate/retire-old workflow (§24.14)
- [ ] Dropdown option management: add/rename/reorder/disable; stable option
      keys, not labels, are the stored value (§10.4)
- [ ] Dropdown options with existing references are retired, not deleted;
      remain visible on existing records/history (§24.15)
- [ ] Required-checkbox semantics: required means "must have true/false",
      not "must be true" (§24.16)
- [ ] Empty optional values normalized to `null` at the API boundary (§24.17)

## Phase 10 — Locations & Preferences

- [ ] Location CRUD (name, parent_id, active) supporting simple hierarchy
      (§24.11)
- [ ] Storage Location optional field wired into `AmmoProduct` admin/edit UI
- [ ] `GET`/`PUT /api/preferences/inventory-view` (§12, §8)

## Phase 11 — Admin: Backup/Restore & CSV Import/Export

- [ ] Backup export covering all entities listed in §24.22
- [ ] Restore validates backup format before touching live data; failed
      restore leaves DB untouched (transactional restore)
- [ ] CSV export: inventory, transaction history, audit history (§24.23)
- [ ] CSV import for ammunition/product data with dry-run/preview,
      row-level error reporting, duplicate-UPC detection, null
      normalization, current field-definition validation (§24.23)

## Phase 12 — API Surface

- [ ] `GET/POST /api/ammo`, `GET/PATCH /api/ammo/{id}`,
      `GET /api/ammo/by-upc/{upc}` — search/sort/pagination/custom-field
      query support (§12)
- [ ] `GET/POST /api/transactions`, `POST /api/transactions/{id}/reverse`
- [ ] `GET/POST /api/admin/fields`, `PATCH /api/admin/fields/{id}`,
      dropdown-option admin endpoints
- [ ] `GET/PUT /api/preferences/inventory-view`
- [ ] `GET /api/scanners` (connected/disconnected state, last scan
      timestamp)
- [ ] `GET /api/locations` (+ CRUD)
- [ ] `GET /api/audit`
- [ ] Backup/restore + CSV import/export endpoints

## Phase 13 — Error Handling & Resilience

- [ ] Scanner disconnected: visible status, auto-reconnect, no app restart
      required (already partially true via `ScannerReader` retry loop) (§24.25)
- [ ] WebSocket disconnected: degraded/reconnecting UI state, auto-reconnect
- [ ] DB failure: mutating ops fail closed, no false-success messages,
      atomic rollback
- [ ] Validation failure: form/modal data preserved, specific errors shown,
      no transaction created
- [ ] Server restart during an open modal: client must revalidate/re-resolve
      on reconnect rather than trusting stale pending state
- [ ] Mutation endpoints revalidate current inventory state server-side
      regardless of what the client displayed (§24.25, §24.26)
- [ ] Reject/re-resolve operations against a record deleted or materially
      changed after the modal opened

## Phase 14 — Testing

Unit tests (§20):
- [ ] UPC resolution (incl. multiple identifiers → one product)
- [ ] Required-field validation rules
- [ ] Numeric custom-field validation
- [ ] Dropdown validation (incl. retired options)
- [ ] Transaction balance calculations
- [ ] Negative-inventory prevention
- [ ] Scanner HID key decoding (`app/scanner.py` keymap/buffer logic)
- [ ] Scan debounce (500ms) and FIFO queue (max 5) logic

API tests (§20):
- [ ] Ammo creation, duplicate-UPC handling, editing
- [ ] Search, sorting, pagination
- [ ] IN / OUT / ADJUST transactions, reversal
- [ ] Transaction history querying/filtering
- [ ] Field administration, custom-field CRUD
- [ ] Persistent inventory-view preferences
- [ ] Idempotent transaction submission (repeated `client_request_id`)

Integration tests (§20):
- [ ] Unknown scan → create AmmoProduct/Identifier → initial RECEIVE
      transaction
- [ ] Known scan → confirmed IN transaction
- [ ] Known scan → confirmed OUT transaction
- [ ] Cancel scan → no transaction, scan marked `CANCELED`
- [ ] Duplicate/pending scan + queue-overflow behavior
- [ ] Transaction rollback on validation/DB failure
- [ ] WebSocket scan delivery end-to-end

## Phase 15 — Deployment / Ops Follow-ups

- [ ] Update Jenkinsfile with an Alembic migration stage
- [ ] Update AGENTS.md once the data model/service layer lands (architecture
      section will be out of date after Phase 1–2)
- [ ] Confirm backup/restore works against the deployed Postgres instance
      on the Pi
- [ ] Re-verify scanner + Docker `devices:` mapping still works after the
      app restructuring

---

## Explicitly Deferred (not part of this checklist, per §21)

Native mobile app, ESP32 client implementation, RFID, external UPC
databases, AI product recognition, supplier management, purchase orders,
cost accounting, cloud sync, multi-user RBAC, loose-round inventory,
open-box tracking, multi-location transfers.
