# Inventory Manager --- Product & Technical Specification

**Status:** Initial V1 specification\
**Target implementation:** Existing `inventory-manager` PoC\
**Primary backend:** Python / FastAPI / PostgreSQL\
**Primary deployment:** Docker Compose on Linux/Raspberry Pi\
**Primary input device:** USB HID UPC barcode scanner\
**Future client:** ESP32 touchscreen terminal

## 1. Purpose

Inventory Manager is an ammunition inventory-control application
centered around scanning the UPC barcode on commercial ammunition
packaging.

The system shall allow a user to scan a box of ammunition, identify it
by UPC, and either create a new ammunition record or perform a confirmed
inventory transaction against an existing record.

The browser-based interface is the primary V1 client. The architecture
must permit a future ESP32 touchscreen client to use the same
server-side API and scan workflow.

## 2. Existing PoC

The existing project already provides:

-   FastAPI application.
-   PostgreSQL persistence through SQLAlchemy.
-   Direct Linux `evdev` access to a USB HID keyboard-wedge barcode
    scanner.
-   Scan-event persistence.
-   WebSocket broadcasting of scanner events.
-   Basic item CRUD API.
-   Basic inventory quantity adjustment.
-   Jinja-based browser interface.
-   Docker / Docker Compose deployment.
-   Jenkins CI/CD deployment.

The V1 implementation should evolve the existing project rather than
replace it unnecessarily.

## 3. Core Design Principles

1.  A barcode scan identifies an ammunition package/SKU; a scan by
    itself MUST NOT change inventory.
2.  Every inventory change MUST require an explicit user confirmation.
3.  Every confirmed inventory change MUST create an immutable
    transaction record.
4.  A second scan MUST NOT silently replace an unresolved scan.
5.  UPC values MUST be unique for active ammunition SKU records.
6.  The application must support ammunition that has no commercial UPC
    through manual/custom identification in future versions; this is not
    required for the initial scanner workflow.
7.  UI display labels and field requirements must be configurable
    without renaming stable internal field keys.
8.  Custom fields must not require database schema migrations.
9.  Server-side APIs should contain business logic so browser and future
    embedded clients behave consistently.

## 4. Terminology

### Ammo SKU

An `AmmoSKU` represents one commercially packaged ammunition SKU
identified by a UPC. Different package sizes of the same underlying load
may therefore be separate SKU records.

Example:

-   Manufacturer: Federal
-   Product Line: American Eagle
-   Cartridge: 9mm Luger
-   Bullet Weight: 124 gr
-   Bullet Type: FMJ
-   Rounds Per Box: 50
-   UPC: package-specific UPC

A 100-round package of the same load may have a different UPC and
therefore be another `AmmoSKU`.

### Box

A package represented by an AmmoSKU. `rounds_per_box` specifies its
contents.

### Transaction

An immutable record describing a confirmed inventory change.

### Scan Event

A record that a barcode payload was received. A scan event is not itself
an inventory transaction.

## 5. Primary Scanner Workflow

### 5.1 Scan Received

When a UPC is scanned:

1.  Scanner service receives and decodes the barcode.
2.  Server records a scan event.
3.  Scan event is delivered to the active web client.
4.  UPC is resolved against the ammunition database.
5.  The client displays either the Unknown UPC workflow or Known UPC
    workflow.
6.  No inventory quantity is changed until the user confirms an
    operation.

### 5.2 Unknown UPC

If the UPC is not present in the database, the UI MUST open a **New
Ammunition** modal.

The scanned UPC MUST be pre-populated and should normally be read-only
in this workflow.

The modal shall display the configured ammunition fields.
Required/optional behavior must come from the field-definition
configuration.

Initial system fields should include:

-   UPC
-   Manufacturer
-   Product Line
-   Manufacturer SKU
-   Cartridge / Caliber
-   Bullet Weight
-   Bullet Type
-   Rounds Per Box
-   Description
-   Storage Location
-   Notes

The modal shall also request an initial box quantity.

On confirmation, the server MUST atomically:

1.  Validate all required fields.
2.  Create the AmmoSKU.
3.  Create the initial inventory `IN`/`RECEIVE` transaction.
4.  Commit both operations or neither operation.
5.  Return the resulting SKU and inventory balance.

### 5.3 Known UPC

If the UPC exists, the UI MUST open an **Inventory Transaction** modal.

The modal shall display enough identifying information to prevent the
user from acting on the wrong ammunition, including at minimum:

-   Manufacturer
-   Product Line
-   Cartridge / Caliber
-   Bullet Weight, if configured
-   Bullet Type, if configured
-   Rounds Per Box
-   UPC
-   Current box quantity
-   Current calculated round quantity

The modal MUST prompt for:

-   Direction: `IN` or `OUT`
-   Quantity of boxes

Quantity shall default to `1`.

`IN` and `OUT` should be large touch-friendly controls suitable for both
desktop browsers and future touchscreen clients.

The transaction MUST NOT occur until the user confirms.

### 5.4 Scan Collision / Pending Scan

Only one unresolved scanner interaction may control a client at a time.

If a second barcode is scanned while a scan modal is unresolved:

-   The current modal MUST NOT be replaced.
-   The new scan should be queued or explicitly reported as pending.
-   The user must be able to complete/cancel the current interaction
    before the next scan is processed.

The implementation must never silently apply an operation intended for
one UPC to another UPC.

## 6. Inventory Accounting

### 6.1 Canonical Values

For V1, each AmmoSKU shall maintain or expose:

-   `box_quantity`
-   `rounds_per_box`
-   `total_rounds`

For sealed-box inventory:

`total_rounds = box_quantity * rounds_per_box`

Loose-round tracking may be added later. The data model should avoid
making that future enhancement unnecessarily difficult.

### 6.2 Transactions

Initial transaction types:

-   `RECEIVE` / UI label `IN`
-   `REMOVE` / UI label `OUT`
-   `ADJUST`

Future transaction types may include:

-   `OPEN_BOX`
-   `CONSUME`
-   `CONSOLIDATE`
-   `TRANSFER`

A transaction should record:

-   Transaction ID
-   Ammo SKU ID
-   Timestamp
-   Transaction type
-   Box quantity delta
-   Round quantity delta
-   Previous box balance
-   New box balance
-   Previous round balance
-   New round balance
-   Location, when applicable
-   Source/client
-   Associated scan event, when applicable
-   Optional notes

Transactions MUST be immutable.

Incorrect inventory must be corrected by creating an `ADJUST`
transaction rather than modifying or deleting historical transactions.

An `OUT` operation MUST fail validation if it would create an invalid
negative inventory balance unless a future administrative policy
explicitly permits negative inventory.

## 7. Web Interface

### 7.1 Primary Areas

V1 web navigation should include:

-   Dashboard / Inventory
-   Transaction History
-   Admin
-   Scanner / System Status

### 7.2 Inventory Search

The user MUST be able to search the inventory database by any configured
searchable field.

Searchable fields may include:

-   UPC
-   Manufacturer
-   Product Line
-   Manufacturer SKU
-   Cartridge / Caliber
-   Bullet Weight
-   Bullet Type
-   Rounds Per Box
-   Box Quantity
-   Total Rounds
-   Description
-   Location
-   Notes
-   Configured custom fields

Search must be server-side rather than limited to rows already loaded in
the browser.

### 7.3 Inventory Sorting

The user MUST be able to sort the inventory table by any sortable field.

Each visible sortable column should allow ascending and descending
order.

Sorting must work with server-side pagination/querying.

### 7.4 Inventory Detail

Selecting an inventory row should expose the full ammunition record and
the transaction history associated with that SKU.

### 7.5 Transaction History

The web interface MUST contain a global transaction-history view.

History should expose:

-   Timestamp
-   Action/type
-   Manufacturer
-   Product Line
-   Cartridge
-   UPC
-   Box quantity change
-   Round quantity change
-   Previous balance
-   New balance
-   Location
-   Source/client
-   Notes

The history view MUST support:

-   Global search
-   Sorting by sortable fields
-   Date-range filtering
-   Transaction-type filtering
-   Filtering by ammunition/SKU
-   Filtering by cartridge/caliber
-   Filtering by manufacturer
-   Filtering by source/client

Newest transactions should be the default sort order.

## 8. Persistent Inventory View Configuration

The default inventory view MUST be configurable.

A user-facing settings control shall allow selection of:

-   Visible columns
-   Column order
-   Default sort field
-   Default sort direction
-   Rows per page

These preferences MUST persist server-side and MUST be restored when the
interface is reopened.

Search text and temporary filters SHOULD NOT automatically become part
of the saved default view.

The design should allow future named/saved views without requiring a
major redesign.

Example future views:

-   Default
-   Range Ammo
-   Defensive Ammo
-   Low Stock
-   9mm
-   Rifle Ammo

## 9. Admin Section

### 9.1 Field Administration

The Admin section MUST contain a field-management interface.

For each system or custom field, an administrator shall be able to
configure:

-   Display name
-   Required / optional
-   Enabled / disabled where permitted
-   Display/order position
-   Searchable status where applicable

Stable internal field keys MUST NOT change when an administrator changes
a display name.

Example:

Internal key: `bullet_type`\
Default display name: `Bullet Type`\
Administrator display name: `Projectile Type`

All applicable UI surfaces should then display `Projectile Type` while
application code and stored relationships continue using `bullet_type`.

### 9.2 Required Fields

Administrators MUST be able to mark supported fields as required or
optional.

Required-field validation MUST be enforced server-side. Client-side
validation should additionally provide immediate feedback.

Changing an existing optional field to required MUST NOT destroy or hide
existing records that lack the value.

Existing incomplete records remain readable. When such a record is
edited, the current required-field rules shall be enforced before
saving.

Some core fields may be permanently required by system design. The admin
UI should clearly identify fields whose required status cannot safely be
disabled.

### 9.3 System Fields

System fields have stable application semantics.

System fields may support:

-   Display-name changes
-   Required-state changes where safe
-   Enabled-state changes where safe
-   Display-order changes

Critical system fields such as UPC and Rounds Per Box must not be
deletable.

## 10. Custom Fields

Administrators MUST be able to create custom ammunition fields.

Creating a custom field MUST NOT require a database migration.

### 10.1 Common Custom Field Properties

A custom field definition should support:

-   Stable internal key
-   Display name
-   Field/control type
-   Required
-   Enabled
-   Searchable
-   Sort/display order
-   Type-specific configuration
-   Created timestamp
-   Updated timestamp

### 10.2 Textbox

Textbox custom fields shall support two value modes:

#### Text / Alphanumeric

Accepts arbitrary permitted textual/alphanumeric content.

Stored as a string/text value.

#### Number

Accepts numeric values including real/decimal numbers.

The server MUST use an appropriate decimal/numeric representation for
persisted values rather than relying on binary floating-point where
exact persistence is desirable.

Validation must reject non-numeric input.

### 10.3 Checkbox

Checkbox fields represent boolean values.

Supported values:

-   `true`
-   `false`

The field definition may support a configured default value.

### 10.4 Dropdown

Dropdown fields contain administrator-configured options.

Administrators must be able to:

-   Add options
-   Rename option labels
-   Reorder options
-   Disable/retire options

Existing records MUST remain valid if an option is retired.

Dropdown values should reference stable option identifiers rather than
storing the display label as the authoritative value. Renaming a
dropdown option must therefore not require rewriting existing ammunition
records.

## 11. Proposed Data Model

Exact SQLAlchemy implementation is left to the implementing agent, but
the domain should approximately support the following entities.

### 11.1 AmmoSKU

Core system-defined ammunition/package data.

Suggested fields:

-   `id`
-   `upc`
-   `manufacturer`
-   `product_line`
-   `manufacturer_sku`
-   `cartridge`
-   `bullet_weight_gr`
-   `bullet_type`
-   `rounds_per_box`
-   `description`
-   `notes`
-   `created_at`
-   `updated_at`

Do not assume all optional fields will remain hard-coded forever.

### 11.2 InventoryTransaction

Suggested fields:

-   `id`
-   `ammo_sku_id`
-   `scan_event_id`
-   `transaction_type`
-   `box_delta`
-   `round_delta`
-   `previous_box_balance`
-   `new_box_balance`
-   `previous_round_balance`
-   `new_round_balance`
-   `location_id`
-   `source`
-   `notes`
-   `created_at`

### 11.3 ScanEvent

Suggested fields:

-   `id`
-   `payload`
-   `barcode_format`, when known
-   `ammo_sku_id`, nullable
-   `scanner_id`, nullable
-   `scanned_at`

### 11.4 FieldDefinition

Suggested fields:

-   `id`
-   `field_key`
-   `display_name`
-   `field_type`
-   `value_type`
-   `required`
-   `enabled`
-   `searchable`
-   `sort_order`
-   `system_field`
-   `configuration`
-   `created_at`
-   `updated_at`

### 11.5 CustomFieldValue

Custom values should be related to an AmmoSKU rather than dynamically
adding columns to the SKU table.

Possible typed storage:

-   `id`
-   `ammo_sku_id`
-   `field_definition_id`
-   `text_value`
-   `number_value`
-   `boolean_value`

Only the value column appropriate to the field definition should be
populated.

An equivalent PostgreSQL design may be used if it preserves validation,
searching, sorting, and type semantics.

### 11.6 DropdownOption

Suggested fields:

-   `id`
-   `field_definition_id`
-   `stable_key`
-   `label`
-   `sort_order`
-   `enabled`

### 11.7 InventoryView / Preferences

Suggested fields:

-   `id`
-   `name`
-   `is_default`
-   `visible_columns`
-   `column_order`
-   `sort_field`
-   `sort_direction`
-   `page_size`
-   `created_at`
-   `updated_at`

A simpler preference table is acceptable for V1 if it preserves a
straightforward migration path to named views.

## 12. API Requirements

Endpoint names may change during implementation, but the API must expose
equivalent capabilities.

### Ammo

-   `GET /api/ammo`
-   `POST /api/ammo`
-   `GET /api/ammo/{id}`
-   `PATCH /api/ammo/{id}`
-   `GET /api/ammo/by-upc/{upc}`

`GET /api/ammo` must support search, sorting, pagination, and
configurable-field queries.

### Transactions

-   `GET /api/transactions`
-   `POST /api/transactions`

Transaction creation must be the normal mechanism for changing
inventory.

### Fields / Admin

-   `GET /api/admin/fields`
-   `POST /api/admin/fields`
-   `PATCH /api/admin/fields/{id}`
-   endpoints for dropdown-option administration

### Preferences

-   `GET /api/preferences/inventory-view`
-   `PUT /api/preferences/inventory-view`

### Scanner

The scanner subsystem must expose scan events to clients and provide
scanner status.

Potential endpoints/events:

-   `GET /api/scanners`
-   WebSocket scan-event stream
-   scanner connected/disconnected state
-   last scan timestamp

## 13. Scan Event Contract

A scanner WebSocket event should identify the event without directly
changing inventory.

Example:

``` json
{
  "event": "barcode_scanned",
  "scan_id": 1847,
  "code": "029465123456",
  "format": "UPC_A",
  "timestamp": "2026-08-24T13:42:18Z"
}
```

The client or server-side scan-resolution service may then resolve the
UPC.

The architecture must permit future routing of scans to a particular
active terminal instead of assuming every connected WebSocket client
should act on every scan.

## 14. Architecture

Recommended application organization:

``` text
app/
  main.py
  config.py
  db.py

  models/
  schemas/
  routers/
  services/
  repositories/
  hardware/
  templates/
  static/
```

Suggested service responsibilities:

``` text
ScannerReader
    |
    v
ScannerService
    |
    v
ScanProcessor
    |
    v
Identifier / UPC Resolver
    |
    v
Inventory Service
    |
    +--> Transaction Service
    |
    +--> WebSocket/Event Broadcaster
```

HTTP routes and scanner handlers SHOULD call shared service-layer
business logic rather than independently implementing inventory rules.

## 15. Database Migrations

V1 MUST introduce Alembic or an equivalent migration system.

Do not rely on `Base.metadata.create_all()` as the production
schema-upgrade mechanism once real inventory data is stored.

Database migrations must preserve existing data whenever reasonably
possible.

## 16. Validation and Data Integrity

Server-side validation is authoritative.

At minimum:

-   UPC uniqueness must be enforced.
-   Required fields must be validated from current field definitions.
-   Numeric custom fields must contain valid numeric values.
-   Checkbox values must be boolean.
-   Dropdown values must reference valid options.
-   Retired dropdown options remain valid for existing records.
-   Inventory operations must not silently produce invalid negative
    balances.
-   Transaction and SKU creation for an unknown UPC must be atomic.
-   Duplicate submissions should be guarded against where practical.

## 17. Search and Sort Architecture

Search and sorting must work for both system and supported custom
fields.

The implementation should avoid requiring all records to be loaded into
browser memory.

The backend should support query parameters similar to:

``` text
GET /api/ammo?search=Federal&sort=manufacturer&order=asc&limit=50&offset=0
```

and:

``` text
GET /api/transactions?search=9mm&type=REMOVE&sort=created_at&order=desc
```

Field definitions must indicate whether a field can participate in
search and/or sorting when necessary.

## 18. Browser UX Requirements

-   Modal controls must be usable by mouse, keyboard, and touchscreen.
-   Primary touch targets should be large enough for a future embedded
    touchscreen.
-   Scanner workflows should require minimal typing for known UPCs.
-   Known-UPC quantity defaults to one box.
-   The currently scanned ammunition must be visually obvious before
    confirmation.
-   Destructive or inventory-reducing operations must not be triggered
    solely by scanning.
-   Modal cancellation must leave inventory unchanged.
-   Successful operations should provide immediate visible confirmation.
-   Scanner-disconnected state should be visible without preventing
    manual inventory browsing.

## 19. Future ESP32 Client

The future ESP32 touchscreen is not part of the initial implementation,
but V1 architectural decisions must account for it.

The ESP32 should eventually be able to:

-   Receive or query scan events.
-   Resolve a UPC.
-   Display known ammunition.
-   Display unknown-UPC data-entry workflows where practical.
-   Submit IN/OUT transactions.
-   Display current inventory.
-   Receive validation errors.

Business rules must therefore remain on the server rather than being
browser-only JavaScript logic.

## 20. Testing Requirements

The project should add automated coverage for critical inventory
behavior.

### Unit Tests

-   UPC resolution
-   Required-field rules
-   Numeric custom-field validation
-   Dropdown validation
-   Transaction calculations
-   Negative-inventory prevention
-   Scanner HID key decoding

### API Tests

-   Ammo creation
-   Duplicate UPC handling
-   Ammo editing
-   Search
-   Sorting
-   Pagination
-   IN transactions
-   OUT transactions
-   ADJUST transactions
-   Transaction history
-   Field administration
-   Custom-field CRUD
-   Persistent inventory-view settings

### Integration Tests

-   Unknown scan -\> create AmmoSKU -\> initial RECEIVE transaction
-   Known scan -\> confirmed IN transaction
-   Known scan -\> confirmed OUT transaction
-   Cancel scan -\> no transaction
-   Duplicate/pending scan behavior
-   Transaction rollback on validation/database failure
-   WebSocket scan delivery

## 21. Initial V1 Scope

### In Scope

-   Existing USB HID barcode scanner
-   UPC lookup
-   Unknown-UPC creation modal
-   Known-UPC IN/OUT modal
-   Box-based inventory
-   Immutable transaction history
-   Inventory search by configured fields
-   Inventory sorting
-   Transaction-history search/filter/sort
-   Persistent default inventory table configuration
-   Admin field display-name configuration
-   Admin required-field configuration
-   Custom fields
-   Text/alphanumeric custom fields
-   Real-number custom fields
-   Boolean checkbox custom fields
-   Configurable dropdown custom fields
-   Database migrations
-   Server-side validation
-   Automated tests
-   Existing Docker/Jenkins deployment model

### Explicitly Deferred

Unless added to this specification later:

-   Native mobile application
-   ESP32 implementation
-   RFID
-   External UPC/product databases
-   Automatic product metadata lookup
-   AI product recognition
-   Supplier management
-   Purchase orders
-   Cost accounting
-   Cloud synchronization
-   Multi-user RBAC
-   Loose-round inventory workflow
-   Open-box tracking
-   Multiple physical storage-location transfers

The schema should not intentionally prevent these features from being
added later.

## 22. Implementation Guidance for AI Agents

An AI implementation agent working from this specification should:

1.  Inspect the existing repository before changing architecture.
2.  Preserve working scanner behavior unless a change is necessary.
3.  Prefer incremental, reviewable changes over a full rewrite.
4.  Add database migrations before introducing production schema
    changes.
5.  Keep domain/business logic outside route handlers where practical.
6.  Add or update automated tests with each behavior change.
7.  Do not invent requirements that conflict with this specification.
8.  If a requirement is ambiguous and materially affects data integrity
    or UX, ask for clarification rather than silently choosing
    irreversible behavior.
9.  Prefer backward-compatible migrations.
10. Never make a barcode scan itself mutate inventory.
11. Never modify/delete transaction history as a shortcut for correcting
    inventory.
12. Treat server-side validation as authoritative.
13. Maintain API compatibility for future non-browser clients where
    practical.

## 23. V1 Acceptance Criteria

V1 is functionally complete when all of the following are true:

-   Scanning an unknown UPC opens a new-ammunition workflow.
-   Creating that ammunition produces both the SKU and its initial
    inventory transaction atomically.
-   Scanning a known UPC opens an IN/OUT workflow.
-   The user selects IN or OUT and box quantity before inventory
    changes.
-   Canceling a scan operation leaves inventory unchanged.
-   A pending modal cannot be silently replaced by another scan.
-   Inventory can be searched by configured searchable fields.
-   Inventory can be sorted by supported fields.
-   Transaction history is visible, searchable, sortable, and
    filterable.
-   Transactions are immutable.
-   The default inventory table's visible columns, order, sort, and page
    size persist.
-   Admin can rename supported field display labels.
-   Admin can configure supported fields as required/optional.
-   Admin can create text, numeric, boolean, and dropdown custom fields.
-   Custom fields participate correctly in validation and applicable
    search/display behavior.
-   Dropdown options can be managed without invalidating historical
    records.
-   Production schema changes are migration-driven.
-   Automated tests cover critical scan and inventory workflows.
-   The application continues to deploy through the existing
    Docker/Jenkins approach.

# 24. Clarified Functional Decisions

This section supersedes any earlier wording that conflicts with these decisions.

## 24.1 Multiple UPCs for the Same Ammunition Load

Different UPCs that represent the same underlying ammunition load SHALL resolve to the same inventory item.

The implementation must therefore separate the underlying ammunition record from barcode/package identifiers.

Recommended model:

```text
AmmoProduct
  id
  manufacturer
  product_line
  manufacturer_sku
  cartridge
  bullet_weight_gr
  bullet_type
  description
  notes
  storage_location
  low_stock_threshold
  low_stock_threshold_unit
  created_at
  updated_at
  deleted_at

AmmoPackageIdentifier
  id
  ammo_product_id
  upc
  rounds_per_package
  package_description
  active
  created_at
  updated_at
```

A single `AmmoProduct` may have multiple `AmmoPackageIdentifier` records.

Scanning any active identifier linked to the product SHALL open the same inventory item.

If multiple identifiers represent different package sizes, the transaction workflow MUST use the scanned identifier's `rounds_per_package` when calculating round deltas.

Example:

```text
AmmoProduct:
  Federal HST 9mm 124gr

Identifiers:
  UPC A -> 20 rounds/package
  UPC B -> 50 rounds/package
```

Both UPCs affect the same product inventory, but a scan of UPC A and a scan of UPC B represent different package quantities.

## 24.2 Editing Ammunition Metadata

All editable ammunition fields may be changed after creation.

Every metadata change MUST create an audit/history record containing, at minimum:

- entity type
- entity ID
- field changed
- previous value
- new value
- timestamp
- source/client

Changes to inventory metadata MUST NOT silently rewrite transaction history.

Special care is required when editing fields that affect inventory calculations, especially `rounds_per_package`.

If `rounds_per_package` is changed for an identifier that has existing transactions, the application MUST:

1. display a warning,
2. require explicit confirmation,
3. preserve historical transaction values exactly as originally recorded,
4. apply the new package size only to future transactions.

Transaction rows MUST therefore store their own resolved round delta and relevant package-size snapshot rather than recalculating historical values dynamically from the current identifier definition.

## 24.3 Deletion

Deletion of ammunition records is allowed through the UI.

However, historical transactions, scan records, and audit records MUST remain intact.

Implementation should use logical deletion/tombstoning for records referenced by history:

```text
deleted_at
active = false
```

Deleted ammunition MUST:

- disappear from normal inventory views,
- remain identifiable in historical transactions,
- remain represented in audit history,
- be recoverable through an admin restore function if practical.

The API may expose this as a DELETE operation even if the underlying implementation is a soft delete.

## 24.4 Canceled Scan Events

If a scan opens a modal and the user cancels the workflow:

- inventory MUST remain unchanged,
- no inventory transaction is created,
- the scan event MUST remain in history as informational,
- the scan event status should be recorded as `CANCELED`.

Suggested scan statuses:

- `RECEIVED`
- `RESOLVED`
- `COMPLETED`
- `CANCELED`
- `FAILED`

## 24.5 Scan Queue

Pending scans MUST use FIFO ordering.

Maximum queue depth: **5 scans**.

Behavior:

1. First scan opens the active modal.
2. Additional scans are queued in arrival order.
3. When the active modal is completed or canceled, the next queued scan is processed.
4. The UI SHOULD show the number of queued scans.
5. If the queue already contains 5 pending scans, additional scans MUST be rejected or ignored with a visible/logged queue-overflow event.
6. A queued scan MUST never replace the currently active modal.

## 24.6 Duplicate Scan Debounce

Duplicate scanner input SHALL be suppressed using a **500 ms debounce window**.

A duplicate is defined as:

- same scanner/source,
- same UPC payload,
- received within 500 ms of the previous accepted scan.

After the debounce window expires, scanning the same UPC again is valid and MUST be accepted.

## 24.7 Manual Entry

The web interface MUST include a **Manual Entry** button.

Manual Entry SHALL open a blank ammunition data-entry modal.

The user may populate the same editable fields available during unknown-UPC creation.

Manual Entry MUST NOT require a physical scan.

If a UPC is entered manually, normal UPC uniqueness and resolution rules apply.

Manual creation should use the same server-side validation and business services as scanner-driven creation.

## 24.8 Transaction Reversal

Transaction history MUST provide a **Reverse Transaction** action where reversal is valid.

A reversal MUST NOT modify or delete the original transaction.

Instead, the server creates a new compensating transaction.

The reversal record should include:

```text
reverses_transaction_id
```

and must preserve a clear relationship to the original transaction.

Example:

```text
Original:
RECEIVE +3 packages

Reversal:
ADJUST -3 packages
reverses_transaction_id = <original id>
```

The server MUST validate that the reversal would not violate current inventory rules.

## 24.9 Idempotency and Double-Submit Protection

All inventory-mutating requests MUST support idempotency.

Each client submission shall include a unique request identifier, preferably a UUID:

```text
client_request_id
```

The server MUST ensure that the same request ID cannot create the same logical transaction more than once.

If the same request is retried because of network failure or repeated button presses, the server should return the previously created result rather than create another transaction.

This applies to:

- IN/RECEIVE
- OUT/REMOVE
- ADJUST
- REVERSE
- initial transaction created with a new ammunition record

## 24.10 Structured Source Tracking

Source tracking MUST use structured fields rather than a free-text source string.

Recommended fields:

```text
source_type
source_id
```

Example values:

```text
source_type = "browser"
source_id   = "desktop-default"
```

Future examples:

```text
source_type = "esp32_terminal"
source_id   = "bench-terminal-01"
```

Scan events and transactions should both preserve source information where applicable.

## 24.11 Storage Location

Storage Location SHALL be a default system field.

It SHALL be optional by default.

V1 may use a simple location entity:

```text
Location
  id
  name
  parent_id
  active
```

This permits future hierarchical locations without requiring immediate transfer workflows.

Examples:

```text
Ammo Cabinet
  Shelf 1
  Shelf 2

Safe
```

## 24.12 Low-Stock Thresholds

Each ammunition product may have an optional low-stock threshold.

Thresholds MUST be configurable per product.

The threshold MUST also include its unit.

Supported initial units:

- packages/boxes
- rounds

Example:

```text
low_stock_threshold = 5
low_stock_threshold_unit = "boxes"
```

or:

```text
low_stock_threshold = 500
low_stock_threshold_unit = "rounds"
```

The inventory UI should be able to identify and filter low-stock items.

## 24.13 Custom Field Deletion

A custom field containing existing values MUST NOT be hard-deleted through normal administration.

Instead it SHALL be retired/disabled.

Retired fields:

- are not shown on new-entry forms,
- remain available to existing records/history where necessary,
- remain available to the audit subsystem.

A custom field with no stored values may be permanently deleted.

## 24.14 Custom Field Type Changes

Once a custom field contains stored values, its data type MUST NOT be changed directly.

The supported migration workflow is:

1. create a new custom field with the desired type,
2. migrate values if required,
3. retire the original field.

Display names may be changed freely because internal field keys remain stable.

## 24.15 Dropdown Option Retirement

Dropdown options with existing references MUST NOT be hard-deleted.

A dropdown option may be retired/disabled.

Retired options:

- remain visible for records that already use them,
- remain visible in audit/history,
- cannot be selected for new values.

## 24.16 Required Checkbox Semantics

For checkbox/boolean fields, `required` means the field must contain a boolean value.

Both values are valid:

- `true`
- `false`

Required MUST NOT mean "must be checked."

## 24.17 Null Normalization

Empty optional values SHALL be normalized to `null` at the server boundary where appropriate.

Examples:

```text
"" -> null
whitespace-only optional text -> null
```

The application should avoid treating empty strings and null as separate semantic values unless a specific field requires that distinction.

## 24.18 Global Search Semantics

Global search SHALL behave as follows:

- Text fields: case-insensitive substring matching.
- UPC/barcode values: normalized exact or partial matching where useful, with exact matches ranked first.
- Dropdowns: search against their visible labels.
- Boolean fields: search using human-readable representations where practical.
- Numeric fields: search against normalized textual representations where practical.
- Custom fields marked searchable: included according to their stored data type.

Numeric range filtering is NOT required for V1.

## 24.19 Custom-Field Sorting

Custom fields marked sortable MUST use typed storage and server-side query strategies capable of deterministic sorting.

The database/index strategy should account for this requirement.

## 24.20 Saved Views and Filter Presets

The saved-view model should support:

- visible columns
- column order
- sort field
- sort direction
- page size
- saved filters

V1 only requires the default persistent view.

Future named views may persist filters such as:

- manufacturer
- caliber
- low-stock status
- custom-field values

Temporary search text MUST NOT automatically overwrite the saved default view.

A **Reset to Default** action SHALL be available.

If a saved view references a retired/deleted field, the UI must ignore that field gracefully rather than fail.

## 24.21 Admin Authentication

V1 uses **Option A: no authentication**.

The Admin section is a configuration area, not a protected role-based area.

No login, password, PIN, or RBAC system is required for V1.

The architecture should avoid making future authentication unnecessarily difficult.

## 24.22 Backup and Restore

The Admin page MUST provide backup and restore capabilities.

At minimum, backup must preserve:

- ammunition products
- package identifiers / UPC mappings
- inventory state
- transactions
- scan history
- field definitions
- custom-field values
- dropdown options
- preferences/views
- locations
- audit history

Restore must validate the backup format before modifying live data.

A failed restore MUST NOT leave the database in a partially restored state.

## 24.23 CSV Import / Export

The Admin page MUST provide CSV import/export.

### Export

At minimum:

- inventory export
- transaction-history export
- audit-history export

Custom fields should be represented in exports using stable field keys and/or clearly labeled columns.

### Import

CSV import shall support ammunition/product data.

Import MUST:

- validate before committing,
- report row-level errors,
- avoid partial corrupt imports,
- detect duplicate UPC identifiers,
- normalize empty optional values to null,
- apply current field-definition validation rules.

A preview/dry-run step is strongly recommended before commit.

## 24.24 Data Audit History

Admin MUST expose an audit-history view separate from inventory transaction history.

Audit history tracks configuration and metadata changes.

Suggested fields:

```text
AuditEvent
  id
  entity_type
  entity_id
  action
  field_key
  old_value
  new_value
  source_type
  source_id
  created_at
```

Audit events should cover at least:

- ammunition metadata edits
- deletion/restoration
- field-definition changes
- custom-field creation/retirement
- dropdown-option changes
- preference/view changes where useful
- backup/restore/import operations where practical

Audit records should be immutable.

## 24.25 Error Handling

The UI and API MUST handle failures explicitly.

### Scanner Disconnected

- Display scanner-disconnected status.
- Inventory browsing and manual entry remain available.
- Scanner service should attempt reconnection.
- Reconnection should not require an application restart where practical.

### WebSocket Disconnected

- Display degraded/reconnecting state.
- Attempt automatic reconnection.
- Do not assume missed scans were processed.
- Scan history remains authoritative.

### Database Failure

- Mutating operations fail closed.
- No success message is shown unless the database commit succeeds.
- Atomic operations must roll back completely.

### Validation Failure

- Keep modal/form data intact.
- Display specific validation errors.
- Do not create a transaction.

### Server Restart During Modal

- The browser must not assume the pending modal remains valid.
- On reconnect, stale pending operations should require re-resolution/revalidation.

### Stale Client State

Displayed inventory values are advisory.

The server MUST revalidate current inventory when a transaction is submitted.

### Deleted/Changed Record During Modal

The server must reject or re-resolve a stale operation if the referenced record has been deleted or materially changed after the modal opened.

## 24.26 Single-User Assumption and Data Consistency

V1 assumes one human user.

Full multi-user coordination is therefore not required.

However, the server MUST still preserve transactional consistency because:

- retries may occur,
- multiple browser tabs may exist,
- future ESP32 clients will exist,
- asynchronous scanner events may overlap with UI actions.

Inventory mutation should therefore remain atomic and server-authoritative.

Database transactions and appropriate row locking/atomic update semantics SHOULD be used for inventory changes.

## 24.27 Recommended Structural Additions

The following previously recommended additions are now part of the specification:

- separate underlying ammunition product from UPC/package identifiers,
- editable metadata with audit history,
- delete/archive semantics that preserve history,
- protected package-size history,
- FIFO scan queue with limit 5,
- 500 ms duplicate-scan debounce,
- manual entry workflow,
- transaction reversal,
- idempotent transaction creation,
- structured source tracking,
- optional storage locations,
- per-SKU low-stock thresholds,
- custom-field retirement rules,
- field-type migration rules,
- dropdown retirement rules,
- server-authoritative validation,
- explicit reconnect/error behavior,
- backup/restore,
- CSV import/export,
- audit-history administration.

# 25. Updated Acceptance Criteria

In addition to the earlier V1 acceptance criteria, V1 is not complete until:

- Multiple UPCs may map to the same ammunition product.
- Different UPC package sizes can affect the same product inventory correctly.
- Historical transaction round counts remain unchanged if package metadata is later edited.
- All editable ammunition metadata changes appear in audit history.
- User-visible deletion is supported while transaction/audit history remains intact.
- Canceled scans remain recorded with informational/canceled status.
- Scanner queue is FIFO with a maximum of 5 pending scans.
- Duplicate identical scans from the same source inside 500 ms are suppressed.
- Manual Entry can create ammunition without a scanner.
- Transactions can be reversed using compensating transactions.
- Mutating requests are idempotent.
- Scan and transaction source tracking is structured.
- Storage Location exists as an optional default field.
- Low-stock thresholds can be configured per ammunition product in boxes or rounds.
- Custom fields with data are retired rather than hard-deleted.
- Custom field types cannot be changed after values exist.
- Dropdown options with references can be retired but not destructively removed.
- Required boolean fields accept both true and false.
- Empty optional values normalize to null.
- Global search follows the defined field-specific semantics.
- Sortable custom fields sort server-side using typed values.
- Saved-view architecture supports future filter presets.
- Admin requires no authentication in V1.
- Admin provides backup/restore.
- Admin provides CSV import/export.
- Admin provides immutable audit history.
- Scanner, WebSocket, database, validation, stale-client, and restart errors are handled safely.
- Inventory values are revalidated server-side at mutation time.
