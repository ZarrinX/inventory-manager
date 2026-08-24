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

- [x] Scan event creation never mutates inventory by itself (§3.1, §18)
- [x] UPC resolution against `AmmoPackageIdentifier.upc` (active only)
- [x] WebSocket scan event payload matches the contract in §13
      (`event`, `scan_id`, `code`, `format`, `timestamp`)
- [x] Known-UPC scan → emits enough product detail for the IN/OUT modal
      (§5.3): manufacturer, product_line, cartridge, bullet_weight,
      bullet_type, rounds_per_box, UPC, current box/round balance
- [x] Unknown-UPC scan → emits enough info for the New Ammunition modal
      (§5.2), UPC pre-filled/read-only
- [x] FIFO scan queue, max depth 5, reject/log overflow beyond that (§24.5)
- [x] Only one active/unresolved scan modal at a time; queued scans never
      replace it (§5.4)
- [x] 500ms duplicate-scan debounce per (scanner/source, UPC) (§24.6)
- [x] Cancel workflow: scan status set to `CANCELED`, no transaction created,
      scan remains in history (§24.4)
- [x] Next queued scan is processed after the active modal is
      completed/canceled

## Phase 4 — Inventory Transactions

- [x] `POST /api/transactions` is the only path that mutates inventory
      (§3.2, §12)
- [x] Support `RECEIVE`/`IN`, `REMOVE`/`OUT`, `ADJUST` transaction types
- [x] Unknown-UPC confirm: atomically create `AmmoProduct` +
      `AmmoPackageIdentifier` + initial `RECEIVE` transaction (§5.2)
- [x] Known-UPC confirm: atomically create IN/OUT transaction using the
      scanned identifier's `rounds_per_package` (§24.1)
- [x] Reject `OUT` operations that would produce negative balance (§6.2)
- [x] Transactions are immutable — no update/delete endpoints (§6.2)
- [x] Incorrect inventory corrected via new `ADJUST` transactions only
- [x] Transaction reversal: `POST /api/transactions/{id}/reverse` creates a
      compensating transaction with `reverses_transaction_id`, validates
      against current inventory rules, never mutates the original (§24.8)
- [x] Idempotency: accept `client_request_id` on all mutating transaction
      endpoints; duplicate submissions return the original result instead of
      creating a new transaction (§24.9)
- [x] Historical transactions store their own resolved round delta /
      package-size snapshot rather than recalculating from the current
      identifier definition (§24.2)

## Phase 5 — Editing, Deletion, Audit

- [x] `PATCH` endpoint(s) for editing `AmmoProduct`/`AmmoPackageIdentifier`
      metadata
- [x] Every metadata edit writes an `AuditEvent` (entity, field, old/new
      value, timestamp, source) (§24.2, §24.24)
- [x] Changing `rounds_per_package` on an identifier with existing
      transactions requires explicit confirmation; historical transactions
      keep their original values (§24.2)
- [x] Soft-delete (`deleted_at`, `active=false`) for `AmmoProduct`; deleted
      records disappear from normal views but remain visible in history/audit
      (§24.3)
- [x] Admin restore function for soft-deleted products
- [x] Audit history API + admin UI view, filterable, immutable (§24.24)

## Phase 6 — Web UI: Core Navigation & Scan Modals

- [x] Nav structure: Dashboard/Inventory, Transaction History, Admin,
      Scanner/System Status (§7.1)
- [x] Unknown-UPC "New Ammunition" modal (fields from §5.2, driven by
      `FieldDefinition` config, required box quantity input)
- [x] Known-UPC "Inventory Transaction" modal (identifying info + current
      balance + IN/OUT toggle + box quantity, default 1) (§5.3)
- [x] Large touch-friendly IN/OUT controls (§5.3, §18)
- [x] Pending-scan indicator / queue depth display (§24.5)
- [x] Scanner-disconnected status indicator; inventory browsing/manual entry
      still available while disconnected (§24.25)
- [x] WebSocket-disconnected indicator with auto-reconnect; no assumption
      that missed scans were processed (§24.25)
- [x] Manual Entry button opening the same blank ammunition modal, no scan
      required (§24.7)

## Phase 7 — Web UI: Inventory Table

- [x] Server-side search across all searchable configured fields (§7.2,
      §24.18 semantics per field type)
- [x] Server-side sort across all sortable fields, asc/desc per column
      (§7.3, §24.19)
- [x] Server-side pagination
- [x] Inventory detail view: full record + associated transaction history
      (§7.4)
- [x] Persistent default view: visible columns, column order, default sort
      field/direction, rows per page — saved server-side, restored on reopen
      (§8)
- [x] "Reset to Default" action for the saved view (§24.20)
- [x] Saved view gracefully ignores retired/deleted fields instead of
      failing (§24.20)
- [x] Low-stock filter/indicator using `low_stock_threshold` +
      `low_stock_threshold_unit` (§24.12)

## Phase 8 — Web UI: Transaction History

- [x] Global transaction history view with all columns from §7.5
- [x] Global search across history
- [x] Sort by sortable fields, newest-first default
- [x] Filters: date range, transaction type, ammo/SKU, cartridge/caliber,
      manufacturer, source/client (§7.5)
- [x] Reverse-transaction action available from the history view where valid
      (§24.8)

## Phase 9 — Admin: Field & Custom Field Management

- [x] Field administration UI: display name, required/optional,
      enabled/disabled, display order, searchable (§9.1)
- [x] Enforce required-field validation server-side; client-side validation
      as a UX nicety only (§9.2)
- [x] Changing optional → required does not hide/break existing incomplete
      records; rules enforced only on next edit (§9.2)
- [x] Critical system fields (UPC, rounds-per-package) marked
      non-deletable/permanently required where applicable (§9.3)
- [x] Custom field CRUD: text/alphanumeric, number (decimal), boolean,
      dropdown (§10)
- [x] Custom field creation requires no DB migration (typed value table)
- [x] Custom fields with stored values are retired/disabled, not
      hard-deleted (§24.13)
- [x] Custom fields with no stored values may be hard-deleted
- [x] Field type changes on fields with existing values are blocked; document
      the create-new/migrate/retire-old workflow (§24.14)
- [x] Dropdown option management: add/rename/reorder/disable; stable option
      keys, not labels, are the stored value (§10.4)
- [x] Dropdown options with existing references are retired, not deleted;
      remain visible on existing records/history (§24.15)
- [x] Required-checkbox semantics: required means "must have true/false",
      not "must be true" (§24.16)
- [x] Empty optional values normalized to `null` at the API boundary (§24.17)

## Phase 10 — Locations & Preferences

- [x] Location CRUD (name, parent_id, active) supporting simple hierarchy
      (§24.11)
- [x] Storage Location optional field wired into `AmmoProduct` admin/edit UI
- [x] `GET`/`PUT /api/preferences/inventory-view` (§12, §8)

## Phase 11 — Admin: Backup/Restore & CSV Import/Export

- [x] Backup export covering all entities listed in §24.22
- [x] Restore validates backup format before touching live data; failed
      restore leaves DB untouched (transactional restore)
- [x] CSV export: inventory, transaction history, audit history (§24.23)
- [x] CSV import for ammunition/product data with dry-run/preview,
      row-level error reporting, duplicate-UPC detection, null
      normalization, current field-definition validation (§24.23)

## Phase 12 — API Surface

- [x] `GET/POST /api/ammo`, `GET/PATCH /api/ammo/{id}`,
      `GET /api/ammo/by-upc/{upc}` — search/sort/pagination/custom-field
      query support (§12)
- [x] `GET/POST /api/transactions`, `POST /api/transactions/{id}/reverse`
- [x] `GET/POST /api/admin/fields`, `PATCH /api/admin/fields/{id}`,
      dropdown-option admin endpoints
- [x] `GET/PUT /api/preferences/inventory-view`
- [x] `GET /api/scanners` (connected/disconnected state, last scan
      timestamp)
- [x] `GET /api/locations` (+ CRUD)
- [x] `GET /api/audit`
- [x] Backup/restore + CSV import/export endpoints

## Phase 13 — Error Handling & Resilience

- [x] Scanner disconnected: visible status, auto-reconnect, no app restart
      required (already partially true via `ScannerReader` retry loop) (§24.25)
- [x] WebSocket disconnected: degraded/reconnecting UI state, auto-reconnect
- [x] DB failure: mutating ops fail closed, no false-success messages,
      atomic rollback
- [x] Validation failure: form/modal data preserved, specific errors shown,
      no transaction created
- [x] Server restart during an open modal: client must revalidate/re-resolve
      on reconnect rather than trusting stale pending state
- [x] Mutation endpoints revalidate current inventory state server-side
      regardless of what the client displayed (§24.25, §24.26)
- [x] Reject/re-resolve operations against a record deleted or materially
      changed after the modal opened

## Phase 14 — Testing

Unit tests (§20):
- [x] UPC resolution (incl. multiple identifiers → one product)
- [x] Required-field validation rules
- [x] Numeric custom-field validation
- [x] Dropdown validation (incl. retired options)
- [x] Transaction balance calculations
- [x] Negative-inventory prevention
- [x] Scanner HID key decoding (`app/scanner.py` keymap/buffer logic)
- [x] Scan debounce (500ms) and FIFO queue (max 5) logic

API tests (§20):
- [x] Ammo creation, duplicate-UPC handling, editing
- [x] Search, sorting, pagination
- [x] IN / OUT / ADJUST transactions, reversal
- [x] Transaction history querying/filtering
- [x] Field administration, custom-field CRUD
- [x] Persistent inventory-view preferences
- [x] Idempotent transaction submission (repeated `client_request_id`)

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

- [x] Update Jenkinsfile with an Alembic migration stage
- [x] Update AGENTS.md once the data model/service layer lands (architecture
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
