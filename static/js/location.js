document.addEventListener("DOMContentLoaded", ()=>{
  const select = document.getElementById("deviceSelect");
  const list = document.getElementById("pathList");

  async function refresh(){
    const res = await fetch(`/api/path/${select.value}/`);
    const data = await res.json();
    list.textContent = "";
    for (const p of data.path){
      list.textContent += `${p.ts}  lat:${p.lat}  lon:${p.lon}\n`;
    }
  }
  select.addEventListener("change", refresh);
  refresh();
  setInterval(refresh, 5000);
});
