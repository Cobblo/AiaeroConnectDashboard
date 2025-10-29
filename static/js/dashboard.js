// Single square map: shows one red pin per soldier.
// Click a pin => /person/<person_id>/
// Uses /api/current/; falls back to /api/mock/people/ for demo.

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function fetchPoints() {
  // Real API first
  try {
    const { items = [] } = await getJSON("/api/current/");
    return items
      .filter(it => typeof it.lat === "number" && typeof it.lon === "number")
      .map(it => ({
        id: it.person_id || null,
        name: it.person || it.label || it.device_id,
        lat: it.lat,
        lon: it.lon,
      }));
  } catch {
    // Mock fallback
    const mock = await getJSON("/api/mock/people/");
    const center = { lat: 12.9716, lon: 77.5946 };
    return (mock.people || []).map(p => {
      const last = (p.path && p.path.length) ? p.path[p.path.length - 1] : null;
      return {
        id: p.id,
        name: p.name,
        lat: last ? last.lat : center.lat + (Math.random() - 0.5) * 0.0025,
        lon: last ? last.lon : center.lon + (Math.random() - 0.5) * 0.0025,
      };
    });
  }
}

function renderPins(points) {
  const box = document.getElementById("miniMap");
  const legend = document.getElementById("mapLegend");
  const sub = document.getElementById("mapSubtitle");
  const foot = document.getElementById("deviceCount");

  box.innerHTML = "";
  legend.innerHTML = "";

  if (!points.length) {
    sub.textContent = "no coordinates yet";
    if (foot) foot.textContent = "—";
    return;
  }

  // Fit all points to the box
  let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
  for (const p of points) {
    minLat = Math.min(minLat, p.lat);
    maxLat = Math.max(maxLat, p.lat);
    minLon = Math.min(minLon, p.lon);
    maxLon = Math.max(maxLon, p.lon);
  }
  const padLat = Math.max(0.0004, (maxLat - minLat) * 0.12);
  const padLon = Math.max(0.0004, (maxLon - minLon) * 0.12);
  minLat -= padLat; maxLat += padLat; minLon -= padLon; maxLon += padLon;

  const latR = Math.max(1e-9, maxLat - minLat);
  const lonR = Math.max(1e-9, maxLon - minLon);

  // Place pins
  for (const p of points) {
    const xPct = ((p.lon - minLon) / lonR) * 100;
    const yPct = (1 - (p.lat - minLat) / latR) * 100;

    const pin = document.createElement("div");
    pin.className = "map-pin";
    pin.style.left = xPct + "%";
    pin.style.top = yPct + "%";
    pin.innerHTML = `
      <div class="head"></div>
      <div class="tail"></div>
      <div class="map-label">${p.name}</div>
    `;
    if (p.id) {
      pin.addEventListener("click", e => {
        e.stopPropagation();
        window.location.href = `/person/${p.id}/`;
      });
    }
    box.appendChild(pin);

    const li = document.createElement("div");
    li.innerHTML = `<span class="dot"></span>${p.name}`;
    legend.appendChild(li);
  }

  sub.textContent = `${points.length} device(s) mapped`;
  if (foot) foot.textContent = String(points.length);
}

async function refreshMiniMap() {
  try {
    const points = await fetchPoints();
    renderPins(points);
  } catch (e) {
    console.error("map refresh error:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refreshMiniMap();
  setInterval(refreshMiniMap, 5000); // refresh every 5s
});
