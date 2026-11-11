let lang = localStorage.getItem("sf_lang") || "en";
let selectedZone = null;
const $ = (id)=>document.getElementById(id);
function tr(en, ar){return lang==="ar"?ar:en}
function applyLanguage(){
 document.documentElement.lang=lang; document.documentElement.dir=lang==="ar"?"rtl":"ltr";
 document.querySelectorAll("[data-en]").forEach(el=>{el.textContent=el.dataset[lang]||el.dataset.en});
 $("langBtn").textContent=lang==="en"?"العربية":"English";
 $("pageTitle").textContent=({overview:tr("Farm overview","نظرة عامة على المزرعة"),farm:tr("Farm map","خريطة المزرعة"),soil:tr("Soil analysis","تحليل التربة"),crops:tr("Crop guidance","إرشادات المحاصيل"),plant:tr("Plant image upload","رفع صور النباتات"),robot:tr("Robot connection","توصيل الروبوت")})[document.querySelector(".page.show")?.id||"overview"];
}
$("langBtn").addEventListener("click",()=>{lang=lang==="en"?"ar":"en";localStorage.setItem("sf_lang",lang);applyLanguage();loadAll()});
function showPage(id){document.querySelectorAll(".page").forEach(p=>p.classList.toggle("show",p.id===id));document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("active",n.dataset.page===id));applyLanguage();if(id==="farm")renderFarm();if(id==="soil")renderReadings();if(id==="crops")renderGuidance()}
document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>showPage(b.dataset.page)));
document.querySelectorAll("[data-goto]").forEach(b=>b.addEventListener("click",()=>showPage(b.dataset.goto)));
$("today").textContent=new Date().toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"});
let zones=[];
async function api(url,opts={}){const r=await fetch(url,opts);let d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||"Request failed");return d}
async function loadAll(){
 try{
  const d=await api("/api/dashboard");$("apiState").textContent="Connected";$("zonesTotal").textContent=d.zones_total;$("zonesData").textContent=d.zones_with_data;$("readingCount").textContent=d.readings_total;$("imageCount").textContent=d.plant_images_total;
  const z=await api("/api/zones");zones=z.zones;renderMiniMap();
  if($("farmMap"))renderFarm();
  if(document.querySelector(".page.show")?.id==="soil")renderReadings();
  if(document.querySelector(".page.show")?.id==="crops")renderGuidance();
 }catch(e){$("apiState").textContent="Offline";console.error(e)}
}
function makeCell(z,mini=false){const b=document.createElement("button");b.className="map-cell"+(z.reading?" has":"")+(selectedZone===z.zone_id?" selected":"");b.title=z.zone_id;b.setAttribute("aria-label",z.zone_id);b.addEventListener("click",()=>{selectedZone=z.zone_id;renderFarm()});return b}
function renderMiniMap(){const box=$("miniMap");box.innerHTML="";zones.forEach(z=>box.appendChild(makeCell(z,true)))}
function renderFarm(){const box=$("farmMap");if(!box)return;box.innerHTML="";zones.forEach(z=>box.appendChild(makeCell(z)));renderZoneDetails()}
function fmt(v,unit=""){return v===null||v===undefined?"—":`${v}${unit}`}
function renderZoneDetails(){const box=$("zoneDetails");if(!selectedZone){box.innerHTML=`<div class="empty-state">⌖<h3>${tr("No zone selected","لم يتم اختيار منطقة")}</h3><p>${tr("Choose a cell on the map.","اختر خلية من الخريطة.")}</p></div>`;return}
 const z=zones.find(x=>x.zone_id===selectedZone);const r=z?.reading;
 box.innerHTML=`<h3 class="zone-title">${selectedZone}</h3><p class="small-muted">${r?tr("Latest sensor reading","أحدث قراءة حساسات"):tr("No readings received yet","لم يتم استلام قراءات بعد")}</p>
 ${["moisture","soil_temp","ph","ec"].map((k,i)=>`<div class="metric"><span>${["Moisture","Soil temperature","pH","EC"][i]}</span><b>${fmt(r?.[k],["%"," °C","",""][i])}</b></div>`).join("")}
 ${r?`<div class="note-box"><b>${tr("Preliminary note","ملاحظة استرشادية")}</b><p>${lang==="ar"?z.recommendation.detail_ar:z.recommendation.detail}</p></div>`:""}`;
}
async function renderReadings(){try{const d=await api("/api/readings");const body=$("readingsTable");body.innerHTML=d.readings.length?d.readings.map(r=>`<tr><td><b>${r.zone_id}</b></td><td>${fmt(r.moisture)}</td><td>${fmt(r.soil_temp)}</td><td>${fmt(r.ph)}</td><td>${fmt(r.ec)}</td><td>${new Date(r.created_at).toLocaleString()}</td></tr>`).join(""):`<tr><td colspan="6" class="muted">${tr("No sensor data received yet.","لم يتم استلام بيانات حساسات بعد.")}</td></tr>`}catch(e){console.error(e)}}
function renderGuidance(){const box=$("cropGuidance");const list=zones.filter(z=>z.reading);if(!list.length){box.innerHTML=`<div class="empty-state">♧<p>${tr("No measurements available yet.","لا توجد قياسات متاحة حتى الآن.")}</p></div>`;return}
 box.innerHTML=list.slice(0,32).map(z=>`<div class="guidance-card"><h4>${tr("Zone","المنطقة")} ${z.zone_id} · ${lang==="ar"?z.recommendation.label_ar:z.recommendation.label}</h4><p>${lang==="ar"?z.recommendation.detail_ar:z.recommendation.detail}</p><span class="badge">${tr("Screening score","درجة الفحص")}: ${z.recommendation.score}/100</span></div>`).join("")}
$("refreshBtn").addEventListener("click",loadAll);
$("uploadForm").addEventListener("submit",async e=>{e.preventDefault();const msg=$("uploadMessage"),out=$("aiResult");msg.textContent=tr("Uploading and running AI screening…","جارٍ رفع الصورة وتشغيل فحص الذكاء الاصطناعي…");out.innerHTML="";try{const d=await api("/api/plant-images",{method:"POST",body:new FormData(e.target)});msg.textContent=tr("Image saved.","تم حفظ الصورة.");const a=d.diagnosis||{};if(a.top_predictions){out.innerHTML=`<h4>${tr("AI screening candidates","النتائج المحتملة للفحص")}</h4><p>${a.status==="uncertain"?tr("Uncertain result. Do not treat based on this output.","النتيجة غير مؤكدة. لا تتخذ قرار علاج بناءً عليها."):""}</p>${a.top_predictions.map((x,i)=>`<div class="metric"><span>${i+1}. ${x.crop} — ${x.condition}</span><b>${(x.confidence*100).toFixed(1)}%</b></div>`).join("")}<p>${a.message||""}</p>`}else{out.innerHTML=`<p>${a.message||tr("AI model unavailable.","نموذج الذكاء الاصطناعي غير متاح.")}</p>`}loadAll()}catch(err){msg.textContent=err.message}});
applyLanguage();loadAll();setInterval(loadAll,30000);
