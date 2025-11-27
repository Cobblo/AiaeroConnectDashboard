const ACTIVE_MINUTES = 2;
const API_URL = `/api/current/recent/?active_minutes=${ACTIVE_MINUTES}`;
async function getJSON(url){ const r=await fetch(url,{cache:'no-store'}); if(!r.ok) throw new Error(r.status); return r.json(); }
const isoToDate=s=>new Date(s); const minutesAgo=d=>(Date.now()-+d)/60000;

let map, markers={}, distanceLayers=[], itemsCache=[];
function createMapIfNeeded(){ if(map) return; map=L.map('liveMap',{zoomControl:true,attributionControl:false}).setView([13.0827,80.2707],13);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map); setTimeout(()=>map.invalidateSize(),60); }

function haversine(a,b,c,d){const R=6371000;const toRad=g=>g*Math.PI/180;const e=toRad(c-a),f=toRad(d-b);const g=Math.sin(e/2)**2+Math.cos(toRad(a))*Math.cos(toRad(c))*Math.sin(f/2)**2;return R*2*Math.atan2(Math.sqrt(g),Math.sqrt(1-g));}
function clearDistanceLayers(){distanceLayers.forEach(l=>map.removeLayer(l));distanceLayers=[];document.getElementById("distanceOverlay").style.display="none";}
function showDistancesFrom(id){const o=itemsCache.find(x=>x.device_id===id);if(!o)return;clearDistanceLayers();const overlay=document.getElementById("distanceOverlay");const lines=[];for(const x of itemsCache){if(x.device_id===id)continue;const dist=haversine(o.lat,o.lon,x.lat,x.lon);if(dist>0&&dist<5000){const mid=[(o.lat+x.lat)/2,(o.lon+x.lon)/2];const line=L.polyline([[o.lat,o.lon],[x.lat,x.lon]],{color:'#00e5ff',dashArray:'4,4',weight:1}).addTo(map);const txt=dist<1000?`${dist.toFixed(0)} m`:`${(dist/1000).toFixed(2)} km`;const label=L.divIcon({className:'distance-label',html:txt});const marker=L.marker(mid,{icon:label,interactive:false}).addTo(map);distanceLayers.push(line,marker);lines.push(`${id} — ${txt} — ${x.device_id}`);} } if(lines.length){overlay.innerHTML=`<strong>${id}</strong>`+lines.join("<br>");overlay.style.display="block";}}
function upsertMarker(it){const id=it.device_id,lat=+it.lat,lon=+it.lon;if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const label=it.label??id,isReceiver=id.startsWith("RX"),iconColor=isReceiver?"red":"blue";const icon=L.icon({iconUrl:`https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${iconColor}.png`,shadowUrl:"https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-shadow.png",iconSize:[25,41],iconAnchor:[12,41],popupAnchor:[1,-34],shadowSize:[41,41]});
if(!markers[id])markers[id]=L.marker([lat,lon],{icon}).addTo(map);else{markers[id].setLatLng([lat,lon]);markers[id].setIcon(icon);}
markers[id].bindTooltip(label,{permanent:true,direction:'top',offset:[0,-30],className:'device-label'});markers[id].on('mouseover',()=>showDistancesFrom(id));markers[id].on('mouseout',()=>clearDistanceLayers());
markers[id].bindPopup(`<div style="font-size:13px;"><strong>Device:</strong> ${label}<br><a href="/person/${id}/" style="color:#00e5ff;text-decoration:underline;">View Details →</a></div>`);markers[id].on('dblclick',()=>{window.location.href=`/person/${id}/`;});}
function clearAllMarkers(){for(const k in markers){try{map.removeLayer(markers[k]);}catch{}}clearDistanceLayers();markers={};}
async function refresh(){createMapIfNeeded();try{const data=await getJSON(API_URL);const items=(data.items||[]).filter(p=>Number.isFinite(+p.lat)&&Number.isFinite(+p.lon)&&minutesAgo(isoToDate(p.ts))<=ACTIVE_MINUTES);itemsCache=items;
document.getElementById('liveCount').textContent=`${items.length} device(s) online`;document.getElementById('mapBadge').textContent=`${items.length} device(s) online`;clearAllMarkers();for(const it of items)upsertMarker(it);if(items.length)map.fitBounds(L.latLngBounds(items.map(p=>[p.lat,p.lon])).pad(0.3));}
catch(e){console.error(e);clearAllMarkers();document.getElementById('liveCount').textContent='No devices online';document.getElementById('mapBadge').textContent='No devices online';}}
window.addEventListener("load",()=>{createMapIfNeeded();refresh();setInterval(refresh,5000);});
