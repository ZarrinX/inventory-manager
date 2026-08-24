const statusEl = document.getElementById("scan-status");
const scanPanel = document.getElementById("scan-panel");
const scanUpc = document.getElementById("scan-upc");
const scanKnown = document.getElementById("scan-known");
const scanUnknown = document.getElementById("scan-unknown");
const scanName = document.getElementById("scan-name");
const scanBoxQty = document.getElementById("scan-box-qty");
const scanRoundQty = document.getElementById("scan-round-qty");
const newProductForm = document.getElementById("new-product-form");
const ammoTableBody = document.querySelector("#ammo-table tbody");

let currentUpc = null;

function connect() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/scans`);

  ws.onopen = () => {
    statusEl.textContent = "Connected — ready to scan";
    statusEl.classList.add("connected");
  };
  ws.onclose = () => {
    statusEl.textContent = "Disconnected — retrying…";
    statusEl.classList.remove("connected");
    setTimeout(connect, 2000);
  };
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    showScan(data);
  };
}

function showScan(data) {
  currentUpc = data.upc;
  scanUpc.textContent = data.upc;
  scanPanel.hidden = false;

  if (data.product) {
    scanKnown.hidden = false;
    scanUnknown.hidden = true;
    scanName.textContent = [data.product.manufacturer, data.product.product_line, data.product.cartridge]
      .filter(Boolean)
      .join(" — ");
    scanBoxQty.textContent = data.product.box_quantity;
    scanRoundQty.textContent = data.product.round_quantity;
    updateRow(data.product);
  } else {
    scanKnown.hidden = true;
    scanUnknown.hidden = false;
  }
}

function updateRow(product) {
  let row = ammoTableBody.querySelector(`tr[data-product-id="${product.id}"]`);
  if (!row) {
    row = document.createElement("tr");
    row.dataset.productId = product.id;
    row.innerHTML = `<td class="manufacturer"></td><td class="product-line"></td><td class="cartridge"></td>
      <td class="box-qty"></td><td class="round-qty"></td>`;
    ammoTableBody.appendChild(row);
  }
  row.querySelector(".manufacturer").textContent = product.manufacturer;
  row.querySelector(".product-line").textContent = product.product_line || "";
  row.querySelector(".cartridge").textContent = product.cartridge;
  row.querySelector(".box-qty").textContent = product.box_quantity;
  row.querySelector(".round-qty").textContent = product.round_quantity;
}

newProductForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentUpc) return;
  const formData = new FormData(newProductForm);
  const payload = {
    upc: currentUpc,
    manufacturer: formData.get("manufacturer"),
    product_line: formData.get("product_line") || null,
    cartridge: formData.get("cartridge"),
    bullet_weight_gr: formData.get("bullet_weight_gr") || null,
    bullet_type: formData.get("bullet_type") || null,
    rounds_per_package: Number(formData.get("rounds_per_package")),
    initial_box_quantity: Number(formData.get("initial_box_quantity")),
  };
  const res = await fetch("/api/ammo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    const product = await res.json();
    updateRow(product);
    scanKnown.hidden = false;
    scanUnknown.hidden = true;
    scanName.textContent = [product.manufacturer, product.product_line, product.cartridge]
      .filter(Boolean)
      .join(" — ");
    scanBoxQty.textContent = product.box_quantity;
    scanRoundQty.textContent = product.round_quantity;
    newProductForm.reset();
  }
});

connect();
