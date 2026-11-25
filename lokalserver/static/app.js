"use strict";
const $ = id => document.getElementById(id);
const statuses = {pending:"Afventer",running:"I gang",completed:"Afsluttet"};
const time = value => new Date(value).toLocaleString("da-DK");
let offset = 0, total = 0, minimum = 0, busy = false, refreshQueued = false;
async function api(path) {
  const response = await fetch(path, {cache:"no-store", signal:AbortSignal.timeout(7000)});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function message(id, text, type="") { $(id).textContent=text; $(id).classList.remove("error","warning"); if(type) $(id).classList.add(type); }
function cell(row, text, className="") { const td=document.createElement("td"); td.textContent=text; if(className) td.className=className; row.append(td); return td; }
async function loadHistory() {
  const query=new URLSearchParams({limit:25,offset});
  if ($("station").value) query.set("station",$("station").value);
  if ($("status").value) query.set("status",$("status").value);
  try {
    const data=await api(`/api/orders?${query}`); total=data.total; $("history").replaceChildren();
    for(const item of data.items){const row=document.createElement("tr"); cell(row,time(item.created_at)); cell(row,item.request_id,"id");cell(row,`Station ${item.station}`);const badge=document.createElement("span");badge.className=`badge ${item.status}`;badge.textContent=statuses[item.status]||item.status;cell(row,"").append(badge);$("history").append(row);}
    if(!data.items.length){const row=document.createElement("tr");const td=cell(row,"Ingen ture matcher dit valg.");td.colSpan=4;$("history").append(row);}
    $("total").textContent=`${total} ture`;
    message("history-message",total?`Viser ${data.items.length?offset+1:0}–${offset+data.items.length} af ${total}`:"Ingen registrerede ture endnu.");
    $("previous").disabled=offset===0; $("next").disabled=offset+25>=total;
  } catch(error) { $("history").replaceChildren();$("total").textContent="Ikke tilgængelig";message("history-message","Historikken kunne ikke hentes. Prøv Opdater.","error");$("previous").disabled=true;$("next").disabled=true;throw error; }
}
async function statistics() {
  try {
    const data=await api(`/api/statistics?min_completed=${minimum}`); $("chart").replaceChildren();
    const maximum=Math.max(1,...data.stations.map(s=>s.completed));
    for(const station of data.stations){const row=document.createElement("div");row.className="bar-row";const label=document.createElement("span");label.textContent=`Station ${station.station}`;const track=document.createElement("div");track.className="bar-track";const bar=document.createElement("div");bar.className="bar-fill";bar.style.width=`${station.completed/maximum*100}%`;track.append(bar);const value=document.createElement("strong");value.textContent=station.completed;row.append(label,track,value);$("chart").append(row);}
    $("chart").setAttribute("aria-label",data.stations.map(s=>`Station ${s.station}: ${s.completed} afsluttede ture`).join(". ")||"Ingen stationer matcher filteret");
    if(!data.stations.length){const empty=document.createElement("p");empty.className="chart-empty";empty.textContent="Ingen stationer matcher filteret.";$("chart").append(empty);}
    message("stats-message",minimum?`Kun stationer med mindst ${minimum} afsluttede ture vises.`:"Antal afsluttede ture i databasen. Afventer og I gang tælles ikke som afsluttede.");
  } catch(error){$("chart").replaceChildren();$("chart").setAttribute("aria-label","Statistik utilgængelig");message("stats-message","Statistikken kunne ikke hentes.","error");throw error;}
}
async function temperature() {
  try {
    const data=await api("/api/temperature");
    $("temperature").textContent=data.temperature_c===null?"—":Number(data.temperature_c).toLocaleString("da-DK",{minimumFractionDigits:1,maximumFractionDigits:2});
    $("temp-state").textContent={missing:"Ingen måling",fresh:"Seneste måling",stale:"Forældet måling"}[data.state]||"Ukendt";
    message("temp-message",data.state==="missing"?"Der er endnu ikke modtaget en temperatur fra boksen.":data.state==="stale"?"Målingen er over 2 minutter gammel. Temperaturen lige nu er ukendt.":"Modtaget fra bilens medicinrum.",data.state==="stale"?"warning":"");
    $("temp-time").textContent=data.measured_at?`Modtaget: ${time(data.measured_at)}`:"Ingen eksempelværdi vises som en rigtig måling.";
  } catch(error){$("temperature").textContent="—";$("temp-state").textContent="Ingen forbindelse";message("temp-message","Temperaturen kunne ikke hentes.","error");$("temp-time").textContent="Seneste værdi skjules, indtil forbindelsen er tilbage.";throw error;}
}
async function refresh(){if(busy){refreshQueued=true;return;}busy=true;for(const id of ["refresh","station","status","minimum","apply-stats","previous","next"])$(id).disabled=true;const results=await Promise.allSettled([loadHistory(),statistics(),temperature()]);const ok=results.every(r=>r.status==="fulfilled");message("connection",ok?"Forbundet til lokalserver":"Nogle data kunne ikke hentes",ok?"":"error");message("updated",`${ok?"Opdateret":"Seneste forsøg"}: ${new Date().toLocaleTimeString("da-DK")}`);for(const id of ["refresh","station","status","minimum","apply-stats"])$(id).disabled=false;$("previous").disabled=results[0].status!=="fulfilled"||offset===0;$("next").disabled=results[0].status!=="fulfilled"||offset+25>=total;busy=false;if(refreshQueued){refreshQueued=false;refresh();}}
$("refresh").addEventListener("click",refresh);
for(const id of ["station","status"])$(id).addEventListener("change",()=>{offset=0;refresh();});
$("apply-stats").addEventListener("click",()=>{if(!$("minimum").reportValidity())return;minimum=Number($("minimum").value)||0;refresh();});
$("previous").addEventListener("click",()=>{offset=Math.max(0,offset-25);refresh();});
$("next").addEventListener("click",()=>{offset+=25;refresh();});
refresh(); setInterval(refresh,20000);
