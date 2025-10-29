// Colors
const C1 = "#4db8ff", C2 = "#00d4ff", C3 = "#cfe7ff";

// HARD stop all animations & keep size stable
Chart.defaults.animation = false;
Chart.defaults.transitions = { active: { animation: { duration: 0 } } };
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;   // we control height in CSS
Chart.defaults.resizeDelay = 250;             // throttle any resize flicker
Chart.defaults.color = "#d6e8ff";
Chart.defaults.borderColor = "#1e2b3d";

const BASE_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { color: "#1e2b3d" } },
    y: { grid: { color: "#1e2b3d" } }
  }
};

function lineCfg(label, color) {
  return {
    type: "line",
    data: { labels: [], datasets: [{
      label, data: [], tension: .35,
      borderColor: color, borderWidth: 2, pointRadius: 0, fill: false
    }]},
    options: BASE_OPTS
  };
}

function barCfg(label, color) {
  return {
    type: "bar",
    data: { labels: [], datasets: [{
      label, data: [],
      backgroundColor: withA(color, .35), borderWidth: 0, borderRadius: 8
    }]},
    options: BASE_OPTS
  };
}

function withA(hex, a) {
  const c = hex.replace("#", "");
  const n = c.length === 3 ? parseInt(c.split("").map(x => x + x).join(""), 16) : parseInt(c, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r},${g},${b},${a})`;
}

async function loadPerson(pid) {
  const r = await fetch(`/api/mock/person/${pid}/`);
  if (!r.ok) throw new Error("No data for person " + pid);
  return r.json();
}

document.addEventListener("DOMContentLoaded", async () => {
  // PID from template (with a fallback to data attribute if needed)
  let pid = window.PID;
  if (!pid || pid === "0") {
    const main = document.querySelector("main[data-pid]");
    pid = main ? main.getAttribute("data-pid") : "0";
  }

  let data;
  try { data = await loadPerson(pid); }
  catch (e) { console.error(e); alert("Failed to load data"); return; }

  // Title + latest
  document.getElementById("titleName").textContent = data.name || "Soldier";
  document.getElementById("subTitle").textContent = `Device ${data.device_id || ""}`;
  const L = data.latest || {};
  const set = (id, v) => document.getElementById(id).textContent = (v ?? "—");
  set("nowHr", L.hr); set("nowSpo2", L.spo2); set("nowTemp", L.temp);
  set("nowSys", L.bp_sys); set("nowDia", L.bp_dia);
  set("nowBat", L.battery); set("nowRssi", L.rssi);

  // Charts (no animation, fixed-height containers)
  const hrChart   = new Chart(document.getElementById("hrChart"),   lineCfg("HR",   C1));
  const spo2Chart = new Chart(document.getElementById("spo2Chart"), lineCfg("SpO₂", C2));
  const tempChart = new Chart(document.getElementById("tempChart"), barCfg("Temp",  C3));
  const bpChart   = new Chart(document.getElementById("bpChart"),   lineCfg("BP",   C1));

  const labels = (data.series && (data.series.ts || data.series.timestamps)) || [];
  hrChart.data.labels = labels;   hrChart.data.datasets[0].data = data.series.hr   || []; hrChart.update("none");
  spo2Chart.data.labels = labels; spo2Chart.data.datasets[0].data = data.series.spo2 || []; spo2Chart.update("none");
  tempChart.data.labels = labels; tempChart.data.datasets[0].data = data.series.temp || []; tempChart.update("none");

  // BP as two lines
  bpChart.data.labels = labels;
  bpChart.data.datasets = [
    { label: "SYS", data: data.series.bp_sys || [], tension: .35, borderColor: C1, borderWidth: 2, pointRadius: 0 },
    { label: "DIA", data: data.series.bp_dia || [], tension: .35, borderColor: C2, borderWidth: 2, pointRadius: 0 }
  ];
  bpChart.update("none");
});
