Chart.defaults.color = "#c7d3ea";
Chart.defaults.borderColor = "#1f2a3d";

function fmtTime(ts){
  try { return new Date(ts).toLocaleTimeString(); } catch { return ts; }
}
function makeChart(metric){
  const ctx = document.getElementById("seriesChart");
  const cfg = {
    type: (metric==="bp" ? "line" : "line"),
    data: { labels: [], datasets: [] },
    options: {
      responsive:true, animation:false, plugins:{legend:{display:false}},
      scales:{ x:{grid:{display:false}} }
    }
  };
  if (metric === "bp"){
    cfg.data.datasets = [
      {label:"SYS", data:[], tension:.35, borderWidth:2, pointRadius:0},
      {label:"DIA", data:[], tension:.35, borderWidth:2, pointRadius:0}
    ];
  } else {
    cfg.data.datasets = [
      {label:metric.toUpperCase(), data:[], tension:.35, borderWidth:2, pointRadius:0}
    ];
  }
  return new Chart(ctx, cfg);
}

async function loadSeries(device, metric, chart){
  const res = await fetch(`/api/series/${device}/${metric}/`);
  const data = await res.json();
  const recentEl = document.getElementById("recentList");
  const labels = [], A=[], B=[];
  recentEl.textContent = "";

  if (metric === "bp"){
    for (const p of data.points){
      labels.push(fmtTime(p.ts));
      A.push(p.sys); B.push(p.dia);
      recentEl.textContent += `${p.ts}  SYS:${p.sys}  DIA:${p.dia}\n`;
    }
    chart.data.labels = labels;
    chart.data.datasets[0].data = A;
    chart.data.datasets[1].data = B;
  } else {
    for (const p of data.points){
      labels.push(fmtTime(p.ts));
      A.push(p.value);
      recentEl.textContent += `${p.ts}  ${metric.toUpperCase()}:${p.value}\n`;
    }
    chart.data.labels = labels;
    chart.data.datasets[0].data = A;

    // Nice y-limits
    const y = chart.options.scales.y || (chart.options.scales.y = {});
    if (metric === "spo2"){ y.min = 80; y.max = 100; }
    if (metric === "hr"){   y.min = 40; y.max = 180; }
    if (metric === "temp"){ y.min = 30; y.max = 45; }
  }
  chart.update();
}

document.addEventListener("DOMContentLoaded", async ()=>{
  const metric = window.METRIC || "hr";
  const select = document.getElementById("deviceSelect");
  const chart = makeChart(metric);

  async function refresh(){ await loadSeries(select.value, metric, chart); }
  select.addEventListener("change", refresh);
  await refresh();
  // Auto-refresh every 5s (offline safe)
  setInterval(refresh, 5000);
});
