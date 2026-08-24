const statusEl = document.getElementById("scan-status");
const scanPanel = document.getElementById("scan-panel");
const scanUpc = document.getElementById("scan-upc");
const scanKnown = document.getElementById("scan-known");
const scanUnknown = document.getElementById("scan-unknown");
const scanName = document.getElementById("scan-name");
const scanQty = document.getElementById("scan-qty");
const newItemForm = document.getElementById("new-item-form");
const itemsTableBody = document.querySelector("#items-table tbody");

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

  if (data.item) {
    scanKnown.hidden = false;
    scanUnknown.hidden = true;
    scanName.textContent = data.item.name;
    scanQty.textContent = data.item.quantity;
    updateRow(data.item);
  } else {
    scanKnown.hidden = true;
    scanUnknown.hidden = false;
  }
}

function updateRow(item) {
  let row = itemsTableBody.querySelector(`tr[data-upc="${item.upc}"]`);
  if (!row) {
    row = document.createElement("tr");
    row.dataset.upc = item.upc;
    row.innerHTML = `<td>${item.upc}</td><td class="name"></td><td class="qty"></td>
      <td><button class="delete-btn" data-upc="${item.upc}">Delete</button></td>`;
    itemsTableBody.appendChild(row);
  }
  row.querySelector(".name")?.replaceChildren(document.createTextNode(item.name));
  row.querySelector(".qty").textContent = item.quantity;
}

async function adjust(upc, delta) {
  const res = await fetch(`/api/items/${encodeURIComponent(upc)}/adjust`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delta }),
  });
  if (res.ok) {
    const item = await res.json();
    scanQty.textContent = item.quantity;
    updateRow(item);
  }
}

document.querySelectorAll(".adjust-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (currentUpc) adjust(currentUpc, Number(btn.dataset.delta));
  });
});

itemsTableBody.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.classList.contains("delete-btn")) return;
  const upc = target.dataset.upc;
  const res = await fetch(`/api/items/${encodeURIComponent(upc)}`, { method: "DELETE" });
  if (res.ok) {
    target.closest("tr")?.remove();
  }
});

newItemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentUpc) return;
  const formData = new FormData(newItemForm);
  const res = await fetch("/api/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upc: currentUpc,
      name: formData.get("name"),
      quantity: Number(formData.get("quantity")),
    }),
  });
  if (res.ok) {
    const item = await res.json();
    updateRow(item);
    scanKnown.hidden = false;
    scanUnknown.hidden = true;
    scanName.textContent = item.name;
    scanQty.textContent = item.quantity;
    newItemForm.reset();
  }
});

connect();
