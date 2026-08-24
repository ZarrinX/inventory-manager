const websocketStatus = document.getElementById("scan-status");
const scannerStatus = document.getElementById("scanner-status");
const systemScannerStatus = document.getElementById("system-scanner-status");
const systemWebsocketStatus = document.getElementById("system-websocket-status");
const pendingScans = document.getElementById("pending-scans");
const ammoTableBody = document.querySelector("#ammo-table tbody");
const ammoTableHead = document.querySelector("#ammo-table thead");
const inventorySearch = document.getElementById("inventory-search");
const lowStockOnly = document.getElementById("low-stock-only");
const inventorySort = document.getElementById("inventory-sort");
const sortDirectionButton = document.getElementById("inventory-sort-direction");
const pageSizeSelect = document.getElementById("inventory-page-size");
const pageSummary = document.getElementById("page-summary");
const newAmmoModal = document.getElementById("new-ammo-modal");
const transactionModal = document.getElementById("transaction-modal");
const newProductForm = document.getElementById("new-product-form");
const transactionForm = document.getElementById("transaction-form");
const newAmmoMessage = document.getElementById("new-ammo-message");
const newAmmoError = document.getElementById("new-ammo-error");
const transactionError = document.getElementById("transaction-error");
const transactionProduct = document.getElementById("transaction-product");
const productDetailModal = document.getElementById("product-detail-modal");
const productDetailContent = document.getElementById("product-detail-content");
const adminFieldsBody = document.querySelector("#admin-fields-table tbody");
const adminFieldError = document.getElementById("admin-field-error");
const locationsTableBody = document.querySelector("#locations-table tbody");
const locationParentSelect = document.getElementById("location-parent");
const ammoImportForm = document.getElementById("ammo-import-form");
const importResult = document.getElementById("import-result");
const restoreBackupForm = document.getElementById("restore-backup-form");
const historyTableBody = document.querySelector("#history-table tbody");
const historySearch = document.getElementById("history-search");

let currentScanId = null;
let currentUpc = null;
let currentProduct = null;
let scanModalOpen = false;
let deferredActiveScan = null;
let inventoryView = { visible_columns: ["manufacturer", "product_line", "cartridge", "box_quantity", "round_quantity"], column_order: ["manufacturer", "product_line", "cartridge", "box_quantity", "round_quantity"], sort_field: "manufacturer", sort_direction: "asc", page_size: 50 };
let inventoryPage = 1;
let inventoryTotal = 0;
let historyPage = 1;
let historyDirection = "desc";
const productFieldKeys = new Set(["upc", "manufacturer", "product_line", "manufacturer_sku", "cartridge", "bullet_weight_gr", "bullet_type", "rounds_per_package", "description", "notes", "storage_location", "initial_box_quantity"]);
const columnLabels = { manufacturer: "Manufacturer", product_line: "Product Line", manufacturer_sku: "Manufacturer SKU", cartridge: "Cartridge", bullet_weight_gr: "Bullet Weight", bullet_type: "Bullet Type", box_quantity: "Boxes", round_quantity: "Rounds" };

// Firefox restricts crypto.randomUUID() to secure contexts. The Pi is served
// over HTTP on a private-network IP, so retain idempotency without requiring
// HTTPS or browser-specific behavior.
function requestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `browser-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function formatErrorDetail(detail, fallback) {
  if (Array.isArray(detail)) {
    return detail.map((error) => {
      const field = error.loc?.filter((part) => part !== "body").join(" ");
      return field ? `${field}: ${error.msg || "Invalid value"}` : (error.msg || "Invalid value");
    }).join(" ");
  }
  return typeof detail === "string" ? detail : fallback;
}

async function responseError(response, fallback) {
  const body = await response.json().catch(() => ({}));
  return formatErrorDetail(body.detail, fallback);
}

function setWebsocketStatus(connected) {
  websocketStatus.textContent = connected ? "WebSocket connected" : "WebSocket reconnecting…";
  websocketStatus.classList.toggle("healthy", connected);
  websocketStatus.classList.toggle("unhealthy", !connected);
  systemWebsocketStatus.textContent = connected ? "Connected" : "Disconnected — retrying automatically";
}

function connect() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/scans`);
  ws.onopen = () => { setWebsocketStatus(true); revalidateActiveScan(); };
  ws.onclose = () => { setWebsocketStatus(false); setTimeout(connect, 2000); };
  ws.onmessage = (event) => handleScanEvent(JSON.parse(event.data));
}

async function revalidateActiveScan() {
  try {
    const response = await fetch("/api/scans/active");
    if (response.status === 204) {
      if (scanModalOpen && currentScanId) dismissModalForRevalidation("The pending scan is no longer active. Please scan again.");
      return;
    }
    if (!response.ok) return;
    const scan = await response.json();
    if (!scanModalOpen) showScan(scan);
    else if (currentScanId !== scan.scan_id) {
      dismissModalForRevalidation("The pending scan changed while disconnected; it was revalidated.");
      showScan(scan);
    }
  } catch (_) {
    // The visible reconnect indicator remains authoritative until this retry succeeds.
  }
}

async function refreshScannerStatus() {
  try {
    const response = await fetch("/api/scanners");
    const scanner = await response.json();
    const text = scanner.connected ? "Scanner connected" : "Scanner disconnected — inventory remains available";
    scannerStatus.textContent = text;
    scannerStatus.classList.toggle("healthy", scanner.connected);
    scannerStatus.classList.toggle("unhealthy", !scanner.connected);
    systemScannerStatus.textContent = scanner.last_scan_at ? `${text}; last scan ${new Date(scanner.last_scan_at).toLocaleString()}` : text;
  } catch (_) {
    scannerStatus.textContent = "Scanner status unavailable";
    scannerStatus.classList.add("unhealthy");
    systemScannerStatus.textContent = "Status unavailable";
  }
}

function handleScanEvent(data) {
  if (data.event === "barcode_scanned") {
    if (scanModalOpen) deferredActiveScan = data;
    else showScan(data);
    return;
  }
  if (data.event === "scan_queued") {
    setPendingCount(data.queue_depth);
  } else if (data.event === "scan_overflow") {
    pendingScans.textContent = "Scan queue is full; the latest scan was rejected.";
  }
}

function setPendingCount(depth) {
  pendingScans.textContent = depth ? `${depth} scan${depth === 1 ? "" : "s"} pending.` : "No pending scans.";
}

function showScan(data) {
  const resolution = data.resolution || { known: false };
  currentScanId = data.scan_id;
  currentUpc = data.code;
  currentProduct = resolution.product || null;
  scanModalOpen = true;
  setPendingCount(data.queue_depth);
  if (currentProduct) openTransactionModal();
  else openNewAmmoModal({ scanned: true });
}

function openNewAmmoModal({ scanned }) {
  newProductForm.reset();
  newAmmoError.textContent = "";
  const upc = newProductForm.elements.upc;
  if (scanned) {
    newAmmoMessage.textContent = `Scanned UPC: ${currentUpc}`;
    upc.value = currentUpc;
    upc.readOnly = true;
  } else {
    newAmmoMessage.textContent = "Enter ammunition details and an optional commercial UPC.";
    upc.value = "";
    upc.readOnly = false;
  }
  newAmmoModal.showModal();
}

function openTransactionModal() {
  transactionError.textContent = "";
  transactionForm.reset();
  const product = currentProduct;
  const details = [
    ["Manufacturer", product.manufacturer], ["Product line", product.product_line],
    ["Cartridge", product.cartridge], ["Bullet weight", product.bullet_weight_gr],
    ["Bullet type", product.bullet_type], ["Rounds per box", product.rounds_per_box],
    ["UPC", product.upc], ["Current boxes", product.box_quantity], ["Current rounds", product.round_quantity],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  transactionProduct.replaceChildren(...details.flatMap(([label, value]) => {
    const term = document.createElement("dt"); term.textContent = label;
    const definition = document.createElement("dd"); definition.textContent = value;
    return [term, definition];
  }));
  transactionModal.showModal();
}

function updateRow() { loadInventory(); }

function activeColumns() {
  return inventoryView.column_order.filter((column) => inventoryView.visible_columns.includes(column) && columnLabels[column]);
}

function renderInventory(data) {
  inventoryTotal = data.total;
  inventoryPage = data.page;
  const columns = activeColumns();
  ammoTableHead.innerHTML = `<tr>${columns.map((column) => `<th>${columnLabels[column]}</th>`).join("")}</tr>`;
  ammoTableBody.replaceChildren(...data.items.map((product) => {
    const row = document.createElement("tr"); row.dataset.productId = product.id;
    const isLowStock = product.low_stock_threshold != null && ((product.low_stock_threshold_unit === "boxes" && product.box_quantity <= product.low_stock_threshold) || (product.low_stock_threshold_unit === "rounds" && product.round_quantity <= product.low_stock_threshold));
    row.classList.toggle("low-stock", isLowStock);
    row.tabIndex = 0; row.title = "Open details";
    columns.forEach((column) => { const cell = document.createElement("td"); cell.textContent = product[column] ?? ""; row.appendChild(cell); });
    row.addEventListener("click", () => showProductDetail(product.id));
    return row;
  }));
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  pageSummary.textContent = `${data.total} item${data.total === 1 ? "" : "s"} · page ${data.page} of ${pages}`;
  document.getElementById("previous-page").disabled = data.page <= 1;
  document.getElementById("next-page").disabled = data.page >= pages;
}

async function loadInventory() {
  const params = new URLSearchParams({ page: inventoryPage, page_size: inventoryView.page_size, sort: inventoryView.sort_field || "manufacturer", direction: inventoryView.sort_direction });
  if (inventorySearch.value.trim()) params.set("search", inventorySearch.value.trim());
  if (lowStockOnly.checked) params.set("low_stock", "true");
  const response = await fetch(`/api/ammo?${params}`);
  if (response.ok) renderInventory(await response.json());
}

function populateViewControls() {
  inventorySort.replaceChildren(...Object.entries(columnLabels).map(([key, label]) => { const option = document.createElement("option"); option.value = key; option.textContent = label; return option; }));
  inventorySort.value = inventoryView.sort_field || "manufacturer";
  pageSizeSelect.value = String(inventoryView.page_size);
  sortDirectionButton.textContent = inventoryView.sort_direction === "desc" ? "↓" : "↑";
  const list = document.getElementById("column-options-list");
  list.replaceChildren(...Object.entries(columnLabels).map(([key, label]) => { const labelEl = document.createElement("label"); const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = key; checkbox.checked = inventoryView.visible_columns.includes(key); labelEl.append(checkbox, ` ${label}`); return labelEl; }));
}

async function loadView() {
  const response = await fetch("/api/preferences/inventory-view");
  if (response.ok) inventoryView = await response.json();
  populateViewControls(); loadInventory();
}

async function saveView() {
  inventoryView.visible_columns = [...document.querySelectorAll("#column-options-list input:checked")].map((input) => input.value);
  inventoryView.column_order = Object.keys(columnLabels).filter((column) => inventoryView.visible_columns.includes(column));
  inventoryView.sort_field = inventorySort.value; inventoryView.page_size = Number(pageSizeSelect.value);
  const response = await fetch("/api/preferences/inventory-view", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(inventoryView) });
  if (response.ok) { inventoryView = await response.json(); populateViewControls(); inventoryPage = 1; loadInventory(); }
}

async function showProductDetail(productId) {
  const response = await fetch(`/api/ammo/${productId}`);
  if (!response.ok) return;
  const product = await response.json();
  const identifiers = product.identifiers.map((item) => `<li>${item.upc} · ${item.rounds_per_package} rounds${item.active ? "" : " (inactive)"}</li>`).join("");
  const history = product.transactions.map((item) => `<tr><td>${new Date(item.created_at).toLocaleString()}</td><td>${item.transaction_type}</td><td>${item.box_delta}</td><td>${item.round_delta}</td><td>${item.new_box_balance}</td></tr>`).join("") || "<tr><td colspan=\"5\">No transactions</td></tr>";
  productDetailContent.innerHTML = `<dl class="product-summary"><dt>Manufacturer</dt><dd>${product.manufacturer}</dd><dt>Product line</dt><dd>${product.product_line || ""}</dd><dt>Cartridge</dt><dd>${product.cartridge}</dd><dt>Boxes</dt><dd>${product.box_quantity}</dd><dt>Rounds</dt><dd>${product.round_quantity}</dd></dl><h3>Package identifiers</h3><ul>${identifiers}</ul><h3>Transactions</h3><table><thead><tr><th>When</th><th>Type</th><th>Boxes</th><th>Rounds</th><th>Balance</th></tr></thead><tbody>${history}</tbody></table>`;
  productDetailModal.showModal();
}

async function loadHistory() {
  const params = new URLSearchParams({ page: historyPage, page_size: 50, sort: document.getElementById("history-sort").value, direction: historyDirection });
  const fields = { search: historySearch.value, transaction_type: document.getElementById("history-type").value, ammo_product_id: document.getElementById("history-product-id").value, manufacturer: document.getElementById("history-manufacturer").value, cartridge: document.getElementById("history-cartridge").value, source: document.getElementById("history-source").value, date_from: document.getElementById("history-date-from").value, date_to: document.getElementById("history-date-to").value };
  Object.entries(fields).forEach(([key, value]) => { if (value) params.set(key, value); });
  const response = await fetch(`/api/transactions?${params}`);
  if (!response.ok) return;
  const data = await response.json();
  historyPage = data.page;
  historyTableBody.replaceChildren(...data.items.map((item) => {
    const row = document.createElement("tr");
    const cells = [new Date(item.created_at).toLocaleString(), [item.manufacturer, item.product_line, item.cartridge].filter(Boolean).join(" — "), item.transaction_type, item.box_delta, item.round_delta, item.source_type || ""];
    cells.forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); });
    const actions = document.createElement("td");
    if (!item.is_reversed && !item.reverses_transaction_id) {
      const reverse = document.createElement("button"); reverse.type = "button"; reverse.textContent = "Reverse";
      reverse.addEventListener("click", () => reverseTransaction(item.id)); actions.appendChild(reverse);
    } else actions.textContent = item.is_reversed ? "Reversed" : "Reversal";
    row.appendChild(actions); return row;
  }));
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  document.getElementById("history-page-summary").textContent = `${data.total} transaction${data.total === 1 ? "" : "s"} · page ${data.page} of ${pages}`;
  document.getElementById("history-previous-page").disabled = data.page <= 1;
  document.getElementById("history-next-page").disabled = data.page >= pages;
}

async function reverseTransaction(transactionId) {
  if (!window.confirm("Create a compensating reversal transaction?")) return;
  const response = await fetch(`/api/transactions/${transactionId}/reverse`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client_request_id: requestId() }) });
  if (!response.ok) { window.alert(await responseError(response, "Transaction could not be reversed.")); return; }
  loadHistory(); loadInventory();
}

async function loadAdminFields() {
  const response = await fetch("/api/admin/fields");
  if (!response.ok) return;
  const fields = await response.json();
  adminFieldsBody.replaceChildren(...fields.map((field) => {
    const row = document.createElement("tr");
    [field.display_name, `${field.field_key} · ${field.system_field ? "system" : "custom"}`, `${field.field_type} / ${field.value_type}`, field.required ? "Yes" : "No", field.enabled ? "Yes" : "No", field.searchable ? "Yes" : "No"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); });
    const actions = document.createElement("td");
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => editField(field)); actions.appendChild(edit);
    if (field.field_type === "dropdown") {
      const option = document.createElement("button"); option.type = "button"; option.textContent = "Add option"; option.addEventListener("click", () => addDropdownOption(field.id)); actions.appendChild(option);
      field.options.forEach((item) => { const editOption = document.createElement("button"); editOption.type = "button"; editOption.textContent = `${item.label} (${item.enabled ? "on" : "off"})`; editOption.addEventListener("click", () => editDropdownOption(field.id, item)); actions.appendChild(editOption); });
    }
    if (!field.system_field) { const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Retire"; remove.addEventListener("click", () => deleteField(field.id)); actions.appendChild(remove); }
    row.appendChild(actions); return row;
  }));
}

async function loadLocations() {
  const response = await fetch("/api/locations?include_inactive=true");
  if (!response.ok) return;
  const locations = await response.json();
  const names = new Map(locations.map((location) => [location.id, location.name]));
  locationParentSelect.replaceChildren(new Option("No parent", ""), ...locations.filter((location) => location.active).map((location) => new Option(location.name, location.id)));
  locationsTableBody.replaceChildren(...locations.map((location) => {
    const row = document.createElement("tr");
    [location.name, location.parent_id ? names.get(location.parent_id) || "Unknown" : "", location.active ? "Active" : "Retired"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); });
    const actions = document.createElement("td");
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => editLocation(location)); actions.appendChild(edit);
    if (location.active) { const retire = document.createElement("button"); retire.type = "button"; retire.textContent = "Retire"; retire.addEventListener("click", () => retireLocation(location.id)); actions.appendChild(retire); }
    row.appendChild(actions); return row;
  }));
}

async function editLocation(location) {
  const name = window.prompt("Location name", location.name); if (name === null) return;
  const parentValue = window.prompt("Parent location ID (blank for none)", location.parent_id || ""); if (parentValue === null) return;
  const response = await fetch(`/api/locations/${location.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parentValue ? Number(parentValue) : null }) });
  if (!response.ok) { adminFieldError.textContent = await responseError(response, "Location update failed."); return; }
  loadLocations();
}

async function retireLocation(locationId) {
  if (!window.confirm("Retire this location?")) return;
  const response = await fetch(`/api/locations/${locationId}`, { method: "DELETE" });
  if (response.ok) loadLocations();
}

async function adminRequest(url, method, body) {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) { adminFieldError.textContent = await responseError(response, "Admin update failed."); return null; }
  adminFieldError.textContent = ""; return response;
}

async function editField(field) {
  const display_name = window.prompt("Display name", field.display_name); if (display_name === null) return;
  const required = window.confirm(`Required?\nOK = required, Cancel = optional\nCurrent: ${field.required ? "required" : "optional"}`);
  const enabled = window.confirm(`Enabled?\nOK = enabled, Cancel = disabled\nCurrent: ${field.enabled ? "enabled" : "disabled"}`);
  const searchable = window.confirm(`Searchable?\nOK = searchable, Cancel = not searchable\nCurrent: ${field.searchable ? "searchable" : "not searchable"}`);
  const sort_order = window.prompt("Display order", field.sort_order); if (sort_order === null) return;
  if (await adminRequest(`/api/admin/fields/${field.id}`, "PATCH", { display_name, required, enabled, searchable, sort_order: Number(sort_order) })) loadAdminFields();
}

async function addDropdownOption(fieldId) {
  const stable_key = window.prompt("Stable option key (lowercase_underscores)"); if (!stable_key) return;
  const label = window.prompt("Option label"); if (!label) return;
  if (await adminRequest(`/api/admin/fields/${fieldId}/options`, "POST", { stable_key, label })) loadAdminFields();
}

async function editDropdownOption(fieldId, option) {
  const label = window.prompt("Option label", option.label); if (label === null) return;
  const sort_order = window.prompt("Display order", option.sort_order); if (sort_order === null) return;
  const enabled = window.confirm(`Enabled?\nOK = enabled, Cancel = retired\nCurrent: ${option.enabled ? "enabled" : "retired"}`);
  if (await adminRequest(`/api/admin/fields/${fieldId}/options/${option.id}`, "PATCH", { label, sort_order: Number(sort_order), enabled })) loadAdminFields();
}

async function deleteField(fieldId) {
  if (!window.confirm("Retire or delete this custom field? Existing values cause retirement.")) return;
  if (await adminRequest(`/api/admin/fields/${fieldId}`, "DELETE")) loadAdminFields();
}

async function submitTransaction(payload, errorElement, scanId) {
  const response = await fetch("/api/transactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) {
    errorElement.textContent = await responseError(response, "Transaction could not be completed.");
    return null;
  }
  const result = await response.json();
  updateRow(result.product);
  if (currentScanId === scanId) closeActiveModal();
  return result;
}

newProductForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(newProductForm);
  const scanId = currentScanId;
  const product = Object.fromEntries(form.entries());
  const customFields = {};
  Object.keys(product).forEach((key) => {
    if (!productFieldKeys.has(key)) { customFields[key] = product[key]; delete product[key]; }
  });
  Object.entries(customFields).forEach(([key, value]) => {
    const field = newProductForm.querySelector(`[data-field-key="${key}"]`);
    if (field?.dataset.valueType === "boolean") customFields[key] = value === "true";
  });
  product.custom_fields = customFields;
  product.storage_location_id = product.storage_location ? Number(product.storage_location) : null;
  delete product.storage_location;
  product.initial_box_quantity = Number(product.initial_box_quantity);
  product.rounds_per_package = Number(product.rounds_per_package);
  if (product.bullet_weight_gr === "") product.bullet_weight_gr = null;
  ["product_line", "manufacturer_sku", "bullet_type", "description", "notes"].forEach((field) => { if (product[field] === "") product[field] = null; });
  const payload = { transaction_type: "RECEIVE", new_product: product, client_request_id: requestId() };
  if (scanId) payload.scan_event_id = scanId;
  await submitTransaction(payload, newAmmoError, scanId);
});

transactionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(transactionForm);
  const scanId = currentScanId;
  await submitTransaction({
    transaction_type: form.get("direction"), box_delta: Number(form.get("box_quantity")),
    ammo_product_id: currentProduct.id, scan_event_id: scanId, client_request_id: requestId(),
  }, transactionError, scanId);
});

async function cancelActiveScan() {
  if (!currentScanId) { closeActiveModal(); return; }
  const response = await fetch(`/api/scans/${currentScanId}/cancel`, { method: "POST" });
  if (!response.ok) return;
  const result = await response.json();
  if (!result.next_scan_id) closeActiveModal();
}

function closeActiveModal() {
  newAmmoModal.close(); transactionModal.close();
  currentScanId = null; currentUpc = null; currentProduct = null; scanModalOpen = false;
  if (deferredActiveScan) {
    const next = deferredActiveScan;
    deferredActiveScan = null;
    showScan(next);
  }
}

function dismissModalForRevalidation(message) {
  newAmmoModal.close(); transactionModal.close();
  currentScanId = null; currentUpc = null; currentProduct = null; scanModalOpen = false;
  if (message) websocketStatus.textContent = message;
}

document.querySelectorAll("[data-cancel-modal]").forEach((button) => button.addEventListener("click", cancelActiveScan));
[newAmmoModal, transactionModal].forEach((modal) => modal.addEventListener("cancel", (event) => { event.preventDefault(); cancelActiveScan(); }));
document.getElementById("manual-entry").addEventListener("click", () => {
  if (scanModalOpen) return;
  currentScanId = null; currentUpc = null; currentProduct = null; scanModalOpen = true;
  openNewAmmoModal({ scanned: false });
});
document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".nav-link").forEach((link) => link.classList.toggle("active", link === button));
  document.querySelectorAll("[data-view-panel]").forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== button.dataset.view; });
  if (button.dataset.view === "history") loadHistory();
  if (button.dataset.view === "admin") loadAdminFields();
  if (button.dataset.view === "admin") loadLocations();
}));
document.getElementById("create-field-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const payload = { field_key: form.get("field_key"), display_name: form.get("display_name"), field_type: form.get("field_type"), value_type: form.get("value_type"), required: form.get("required") === "on", searchable: form.get("searchable") === "on" };
  if (await adminRequest("/api/admin/fields", "POST", payload)) { formElement.reset(); loadAdminFields(); }
});
document.getElementById("create-location-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const response = await fetch("/api/locations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), parent_id: form.get("parent_id") ? Number(form.get("parent_id")) : null }) });
  if (!response.ok) { adminFieldError.textContent = await responseError(response, "Location could not be created."); return; }
  formElement.reset(); loadLocations();
});
async function runAmmoImport(commit) {
  const form = new FormData(ammoImportForm);
  if (!form.get("file")?.name) return;
  const response = await fetch(`/api/data/import/ammo.csv?commit=${commit}`, { method: "POST", body: form });
  const result = await response.json().catch(() => ({}));
  importResult.textContent = response.ok ? `${commit ? "Imported" : "Dry run"}: ${result.valid || 0} valid of ${result.rows || 0}; ${result.errors?.length || 0} errors.` : formatErrorDetail(result.detail, "Import failed.");
  if (response.ok && commit) loadInventory();
}
ammoImportForm.addEventListener("submit", (event) => { event.preventDefault(); runAmmoImport(false); });
document.getElementById("commit-import").addEventListener("click", () => { if (window.confirm("Commit this CSV import? Run a dry run first and verify it has no errors.")) runAmmoImport(true); });
restoreBackupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!window.confirm("Restore replaces all current application data. Continue?")) return;
  const file = new FormData(restoreBackupForm).get("file");
  try {
    const backup = JSON.parse(await file.text());
    const response = await fetch("/api/data/restore?confirm_replace=true", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(backup) });
    document.getElementById("restore-result").textContent = response.ok ? "Backup restored." : await responseError(response, "Restore failed.");
    if (response.ok) { loadInventory(); loadAdminFields(); loadLocations(); }
  } catch (_) { document.getElementById("restore-result").textContent = "Choose a valid JSON backup file."; }
});
inventorySearch.addEventListener("input", () => { inventoryPage = 1; loadInventory(); });
lowStockOnly.addEventListener("change", () => { inventoryPage = 1; loadInventory(); });
inventorySort.addEventListener("change", () => { inventoryView.sort_field = inventorySort.value; inventoryPage = 1; loadInventory(); });
sortDirectionButton.addEventListener("click", () => { inventoryView.sort_direction = inventoryView.sort_direction === "asc" ? "desc" : "asc"; sortDirectionButton.textContent = inventoryView.sort_direction === "desc" ? "↓" : "↑"; loadInventory(); });
pageSizeSelect.addEventListener("change", () => { inventoryView.page_size = Number(pageSizeSelect.value); inventoryPage = 1; loadInventory(); });
document.getElementById("previous-page").addEventListener("click", () => { if (inventoryPage > 1) { inventoryPage--; loadInventory(); } });
document.getElementById("next-page").addEventListener("click", () => { inventoryPage++; loadInventory(); });
document.getElementById("save-view").addEventListener("click", saveView);
document.getElementById("reset-view").addEventListener("click", async () => { const response = await fetch("/api/preferences/inventory-view/reset", { method: "POST" }); if (response.ok) { inventoryView = await response.json(); inventoryPage = 1; populateViewControls(); loadInventory(); } });
document.querySelector("[data-close-detail]").addEventListener("click", () => productDetailModal.close());
[historySearch, document.getElementById("history-type"), document.getElementById("history-manufacturer"), document.getElementById("history-cartridge"), document.getElementById("history-product-id"), document.getElementById("history-source"), document.getElementById("history-date-from"), document.getElementById("history-date-to"), document.getElementById("history-sort")].forEach((field) => field.addEventListener(field.type === "search" || field.type === "text" || field.type === "number" ? "input" : "change", () => { historyPage = 1; loadHistory(); }));
document.getElementById("history-sort-direction").addEventListener("click", () => { historyDirection = historyDirection === "desc" ? "asc" : "desc"; document.getElementById("history-sort-direction").textContent = historyDirection === "desc" ? "↓" : "↑"; loadHistory(); });
document.getElementById("history-previous-page").addEventListener("click", () => { if (historyPage > 1) { historyPage--; loadHistory(); } });
document.getElementById("history-next-page").addEventListener("click", () => { historyPage++; loadHistory(); });

connect();
refreshScannerStatus();
setInterval(refreshScannerStatus, 5000);
loadView();
