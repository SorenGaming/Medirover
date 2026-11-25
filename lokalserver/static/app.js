"use strict";
const $ = id => document.getElementById(id);
const statuses = {pending:"Pakkes",running:"Kører",delivered:"Afleveret",completed:"Hjemme",stopped:"Stoppet",cancelled:"Afbrudt",rejected:"Afvist"};
// Knapperne til turen: hvilke statusser de kan bruges i (samme regler som serverens CONTROLS)
const active = ["pending","running","delivered","stopped"];
const buttons = {packed:["pending"], resume:["running","delivered"], stop:active, close:["stopped"]};
const time = value => new Date(value).toLocaleString("da-DK");
const formatReading = value => Number(value).toLocaleString("da-DK", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 2
});
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
    $("temperature").textContent = data.temperature_c === null ? "—" : formatReading(data.temperature_c);
    $("temp-state").textContent={missing:"Ingen måling",fresh:"Seneste måling",stale:"Forældet måling"}[data.state]||"Ukendt";
    message("temp-message",data.state==="missing"?"Der er endnu ikke modtaget en temperatur fra boksen.":data.state==="stale"?"Målingen er over 2 minutter gammel. Temperaturen lige nu er ukendt.":"Modtaget fra bilens medicinrum.",data.state==="stale"?"warning":"");
    $("temp-time").textContent=data.measured_at?`Modtaget: ${time(data.measured_at)}`:"Ingen eksempelværdi vises som en rigtig måling.";
    showHumidity(data);
  } catch(error){$("temperature").textContent="—";$("temp-state").textContent="Ingen forbindelse";message("temp-message","Temperaturen kunne ikke hentes.","error");$("temp-time").textContent="Seneste værdi skjules, indtil forbindelsen er tilbage.";showHumidity(null);throw error;}
}
function showHumidity(data) {
  const humidity = data?.humidity_percent;
  const received = humidity !== null && humidity !== undefined;
  $("humidity").textContent = received ? formatReading(humidity) : "—";
  $("humidity-time").hidden = !received;
  $("humidity-time").textContent = received ? `Modtaget: ${time(data.measured_at)}` : "";
  if (!data) {
    $("humidity-state").textContent = "Ingen forbindelse";
    message("humidity-message", "Luftfugtigheden kunne ikke hentes.", "error");
    return;
  }
  if (!received) {
    $("humidity-state").textContent = "Ingen måling";
    message("humidity-message", data.state === "missing"
      ? "Der er endnu ikke modtaget en måling fra boksen."
      : "Den seneste måling indeholder ingen luftfugtighed.");
    return;
  }
  const stale = data.state === "stale";
  $("humidity-state").textContent = stale ? "Forældet måling" : "Seneste måling";
  message("humidity-message", stale ? "Målingen er over 2 minutter gammel." : "Relativ luftfugtighed i boksen.", stale ? "warning" : "");
}
async function refresh(){if(busy){refreshQueued=true;return;}busy=true;for(const id of ["refresh","station","status","minimum","apply-stats","previous","next"])$(id).disabled=true;const results=await Promise.allSettled([loadHistory(),statistics(),temperature()]);const ok=results.every(r=>r.status==="fulfilled");message("connection",ok?"Forbundet til lokalserver":"Nogle data kunne ikke hentes",ok?"":"error");message("updated",`${ok?"Opdateret":"Seneste forsøg"}: ${new Date().toLocaleTimeString("da-DK")}`);for(const id of ["refresh","station","status","minimum","apply-stats"])$(id).disabled=false;$("previous").disabled=results[0].status!=="fulfilled"||offset===0;$("next").disabled=results[0].status!=="fulfilled"||offset+25>=total;busy=false;if(refreshQueued){refreshQueued=false;refresh();}}
$("refresh").addEventListener("click",refresh);
for(const id of ["station","status"])$(id).addEventListener("change",()=>{offset=0;refresh();});
$("apply-stats").addEventListener("click",()=>{if(!$("minimum").reportValidity())return;minimum=Number($("minimum").value)||0;refresh();});
$("previous").addEventListener("click",()=>{offset=Math.max(0,offset-25);refresh();});
$("next").addEventListener("click",()=>{offset+=25;refresh();});
let trip = null, tripStatus = "", actionError = "";
async function loadTrip() {
  try {
    const newest = (await api("/api/orders?limit=1")).items[0];
    trip = newest && active.includes(newest.status) ? newest : null;
    $("trip-state").textContent = trip ? statuses[trip.status] : "Bilen er ledig";
    $("order").disabled = $("order-station").disabled = trip !== null;
    for (const id in buttons) $(id).disabled = !trip || !buttons[id].includes(trip.status);
    const error = actionError || (trip && trip.last_error ? `Fejl fra bilen: ${trip.last_error}` : "");
    message("trip-message", error || (trip ? `Station ${trip.station} · tur ${trip.request_id}` : "Vælg station og tryk Bestil."), error ? "error" : "");
    if ((trip ? trip.status : "") !== tripStatus) { tripStatus = trip ? trip.status : ""; refresh(); }
  } catch (error) { message("trip-message", "Turen kunne ikke hentes.", "error"); }
}
async function post(path, body) {
  for (const id of ["order", ...Object.keys(buttons)]) $(id).disabled = true;
  actionError = "";
  try {
    const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body || {}), signal:AbortSignal.timeout(7000)});
    if (!response.ok) actionError = `Ikke udført: ${(await response.json().catch(() => ({}))).detail || "HTTP " + response.status}`;
  } catch (error) { actionError = "Ikke udført: ingen forbindelse til serveren."; }
  await loadTrip();
}
$("order").addEventListener("click",()=>post("/api/orders",{request_id:crypto.randomUUID(), station:Number($("order-station").value)}));
for (const id in buttons) $(id).addEventListener("click",()=>post(`/api/orders/${trip.request_id}/${id}`));
refresh(); setInterval(refresh,20000);
loadTrip(); setInterval(loadTrip,2000);
