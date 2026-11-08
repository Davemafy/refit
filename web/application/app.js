"use strict";
// Refit developer workspace. All execution and verification originate at the
// owner-scoped application API; the browser never manufactures evaluation data.
const el=id=>document.getElementById(id);
const page=el("page");
const API="/api/application";
const safe=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const symbols={
 search:'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
 help:'<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 0 1 4.5 1c0 1.9-2.3 2.2-2.3 4"/><path d="M12 17h.01"/>',
 layers:'<path d="m12 2 9 5-9 5-9-5zM3 12l9 5 9-5M3 17l9 5 9-5"/>',
 list:'<path d="M9 6h12M9 12h12M9 18h12M3 6h.01M3 12h.01M3 18h.01"/>',
 pulse:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
 settings:'<path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"/><circle cx="12" cy="12" r="4"/>',
 book:'<path d="M12 6c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1zM12 6v15"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
 back:'<path d="M19 12H5m6-6-6 6 6 6"/>',
 check:'<path d="m4 12 5 5L20 6"/>',
 close:'<path d="M18 6 6 18M6 6l12 12"/>',
 code:'<path d="m8 8-4 4 4 4M16 8l4 4-4 4"/>',
 box:'<path d="m12 2 9 5-9 5-9-5zM3 7v10l9 5 9-5V7M12 12v10"/>',
 git:'<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h6a4 4 0 0 1 4 4v6M6 8v10"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 17v4h16v-4"/>',
 download:'<path d="M12 3v14m-5-5 5 5 5-5M4 18v3h16v-3"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
 file:'<path d="M5 2h9l5 5v15H5zM14 2v5h5M8 12h8M8 16h8"/>',
 shield:'<path d="m12 2 9 4v6c0 6-4 9-9 10-5-1-9-4-9-10V6zM8 12l3 3 5-6"/>',
 alert:'<path d="M12 3 2 21h20zM12 9v5M12 18h.01"/>',
 eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
 lock:'<rect x="4" y="11" width="16" height="11" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>'
};
const ico=name=>'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">'+(symbols[name]||symbols.box)+'</svg>';
for(const target of document.querySelectorAll("[data-icon]"))target.innerHTML=ico(target.dataset.icon);
const C1_DEMO_ID="demo-diagnostic-2026-11-08";
const state={username:null,guest:false,trial:false,demo:null,c1demo:null,c1containment:null,projects:[],runs:[],capabilities:null,wizard:null,tab:"evaluation",stream:null,streamId:null,streamCursor:0,refreshHandle:null,search:null,runRevision:0,evidenceSelected:null,evidenceItems:[],traceFilter:"all",traceSelected:null,traceEvents:[],traceCollapsed:new Set(),runsFilter:"all",runsQuery:"",runsPeriod:"all"};
const statusText={
 compatible_on_sample:"Compatible on evaluated cases",
 verified_adaptation:"Verified repair",
 source_baseline_insufficient:"Source baseline failed",
 export_failed_original_runner_verification:"Export verification failed",
 interrupted:"Interrupted",failed:"Execution failed",
 inference_budget_exhausted:"Budget exhausted",cancelled:"Cancelled",
 queued:"Queued",running:"Running",cancelling:"Cancelling"
};
const ended=status=>!["queued","running","cancelling"].includes(status);
const statusChip=status=>{
 const klass=["compatible_on_sample","verified_adaptation"].includes(status)?"good":ended(status)?"bad":"warn";
 return '<span class="chip '+klass+'"><span class="dot"></span>'+safe(statusText[status]||status||"Unknown")+'</span>';
};
function notify(message){const old=el("pageError");if(old)old.remove();const note=document.createElement("div");note.className="notice";note.id="pageError";note.textContent=message;page.prepend(note);note.scrollIntoView({block:"nearest"});}
async function req(suffix,body,signal){
 const options={credentials:"same-origin",signal};
 if(body instanceof Blob)Object.assign(options,{method:"POST",headers:{"Content-Type":"application/zip"},body});
 else if(body!==undefined)Object.assign(options,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 const response=await fetch(API+suffix,options);
 const payload=await response.json().catch(()=>({}));
 if(response.status===401)throw Error("Your visitor session has expired. Open Import agent to create a fresh workspace.");
 if(!response.ok)throw Error(payload.error?.message||"Request failed ("+response.status+").");
 return payload;
}
const formatTime=value=>{if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString();};
const formatDuration=value=>typeof value==="number"?value.toFixed(1)+" s":"—";
function header(label,step=0,crumb){
 const node=el("crumb");
 node.textContent=label;
 node.title=crumb||label;
 document.body.dataset.workspacePage=label==="Runs"?"runs":"";
 const steps=el("steps");
 steps.hidden=!step;
 el("contextBar").classList.toggle("has-steps",!!step);
 if(step){
  const labels=["Inspect","Configure","Run","Review"];
  steps.innerHTML=labels.map((name,i)=>
   '<span class="step '+(step===i+1?"active":step>i+1?"done":"")+'"'+(step===i+1?' aria-current="step"':'')+'><span class="num">'+(step>i+1?ico("check"):i+1)+'</span>'+name+'</span>'+
   (i===3?"":'<span class="step-sep">—</span>')).join("");
 }
 for(const link of document.querySelectorAll("a[data-nav]")){
   const href=link.getAttribute("href");
   const selected=href==="/app/agents"?location.pathname.startsWith("/app/agents"):href==="/app/runs"?location.pathname.startsWith("/app/runs"):href===location.pathname;
   link.classList.toggle("selected",selected);
   if(link.classList.contains("nav-link")){
    if(selected)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");
   }
 }
 document.title=label+" · Refit";
}
function pageFailure(error){
 const message=error instanceof Error?error.message:"The request did not complete.";
 page.innerHTML='<section class="request-failure request-failure--illustrated" role="alert">'+illustratedAsset("error")+'<div class="request-failure-copy"><h2>Unable to load this view</h2>'+
  '<p>'+safe(message)+'</p><button type="button" class="btn primary" data-action="retry-page">'+
  'Retry loading</button></div></section>';
}
function stopStream(){
 if(state.stream){state.stream.close();state.stream=null;}
 state.streamId=null;state.streamCursor=0;
 if(state.refreshHandle){clearTimeout(state.refreshHandle);state.refreshHandle=null;}
}
function navigate(to,replace=false){
 if(!/^\/app(?:\/|$)/.test(to))return;
 if(replace)history.replaceState({},"",to);else history.pushState({},"",to);
 show().catch(pageFailure);
}
async function ensureGuestSession(){
 if(!state.guest)return;
 const session=await req("/guest-session",{});
 state.username=session.username||"Visitor";
 state.trial=session.guest===true;
 state.guest=false;
 document.body.classList.remove("guest-session");
 el("avatar").textContent="V";
 el("workspaceIdentity").textContent=state.username;
 document.querySelector("[data-trial-start]")?.remove();
 await refreshWorkspace();
}
async function refreshWorkspace(){
 if(state.guest){
   if(!state.demo)state.demo=await req("/demo");
   if(!state.c1demo)state.c1demo=await req("/challenge1-demo");
   if(!state.c1containment){
     // This is a separate *recorded*, root-attested host probe. A missing
     // or mismatched receipt is never presented as successful containment.
     try { state.c1containment=await req("/containment-proof"); }
     catch { state.c1containment={verified:false,unavailable:true}; }
   }
   if(state.c1containment.verified===true)
     state.c1demo.run.containment=state.c1containment;
   state.projects=[];
   state.runs=[state.c1demo.run,state.demo.run];
   return;
 }
 const [projects,runs]=await Promise.all([req("/projects"),req("/runs")]);
 state.projects=projects.projects||[];
 state.runs=runs.runs||[];
}
const lead=(title,subtitle,right="")=>'<div class="page-lead"><div class="page-heading"><h1>'+safe(title)+'</h1><p>'+safe(subtitle)+'</p></div>'+right+'</div>';
// Source artwork is licensed MIT and loaded from our static allowlist. Each
// empty state gets its own subject instead of repeating a generic line icon.
const illustratedAsset=(name,alt="")=>'<span class="context-art" aria-hidden="true">'+
 '<img class="context-art-dark" src="/assets/illustrations/'+name+'-dark.svg" alt="'+safe(alt)+'" loading="lazy" decoding="async">'+
 '<img class="context-art-light" src="/assets/illustrations/'+name+'.svg" alt="'+safe(alt)+'" loading="lazy" decoding="async"></span>';
const empty=(title,desc,button)=>{
 const subject=/^No agents/.test(title)?"folders":/^No runs/.test(title)?"programs":/^No evidence/.test(title)?"lock":null;
 return '<section class="empty empty--editorial" aria-label="'+safe(title)+'">'+
  (subject?illustratedAsset(subject):'<span class="empty-default-icon">'+ico("box")+'</span>')+
  '<div class="empty-editorial-copy"><h2>'+safe(title)+'</h2><p>'+safe(desc)+'</p><div class="empty-editorial-action">'+button+'</div></div></section>';
};
const modelBrand=value=>{
 const id=String(value||"").trim().toLowerCase();
 if(/^(deepseek|deep-seek)/.test(id))return "deepseek";
 if(/^(glm|z[.-]?ai|zhipu)/.test(id))return "zai";
 if(/^(gpt|openai|o[134](?:-|$))/i.test(id))return "openai";
 if(/^(claude|anthropic)/.test(id))return "anthropic";
 if(/^(gemini|gemma|google)/.test(id))return "gemini";
 if(/^(qwen|qwq)/.test(id))return "qwen";
 if(/^(mistral|mixtral|codestral)/.test(id))return "mistral";
 if(/^(llama|meta)/.test(id))return "meta";
 return "generic";
};
const modelMark=value=>'<span class="model-mark model-mark--'+modelBrand(value)+'" aria-hidden="true"></span>';
const modelIdentity=value=>'<span class="model-identity" title="'+safe(value||"Unknown model")+'">'+modelMark(value)+
 '<span class="model-identity-name">'+safe(value||"Unknown model")+'</span></span>';
const importButton=()=>'<button class="btn primary" data-action="new-agent">'+ico("plus")+' Import agent</button>';
const guestNote='<div class="preview-strip">'+ico("eye")+'<span><strong>Recorded evidence.</strong> See an existing migration or import your own agent.</span><button type="button" class="btn compact" data-action="new-agent">Import agent</button></div>';
async function overview(){
 header("Overview");
 await refreshWorkspace();
 if(state.guest){
  const r=state.demo.run;
  const evidence=state.demo.events||[];
  const completed=evidence.filter(e=>e.type==="case_completed");
  const modelCalls=evidence.filter(e=>e.type==="inference_completed");
  const cleanup=evidence.filter(e=>e.type==="sandbox_cleanup"&&e.details?.receipt?.verified===true);
  const recent=evidence.slice(-8).reverse();
  const activity=recent.length?
   '<section class="overview-activity"><div class="overview-activity-head"><h3>Recorded activity</h3>'+
   '<span>'+safe(evidence.length)+' events · '+safe(completed.length)+' case observations · '+safe(modelCalls.length)+' model responses · '+safe(cleanup.length)+' verified cleanups</span></div>'+
   '<div class="overview-event-list">'+recent.map(e=>{
    const d=e.details||{},verified=d.receipt?.verified===true||d.passed===true;
    const failure=d.passed===false||d.receipt?.verified===false||!!d.error;
    return '<button type="button" class="overview-event" data-action="overview-trace" data-id="'+safe(r.id)+'" data-seq="'+safe(e.seq)+'">'+
     '<span class="overview-event-dot '+(failure?"failed":verified?"passed":"")+'"></span>'+
     '<span class="overview-event-name">'+safe(RefitOutcomes.eventLabel(e.type))+'</span>'+
     '<span class="overview-event-context">'+safe([d.case,d.model,d.phase].filter(Boolean).join(" · ")||"Runtime event")+'</span>'+
     '<time class="overview-event-time">'+safe((e.time||"").slice(11,19))+'</time>'+ico("arrow")+'</button>';
   }).join("")+'</div></section>':'';
  const passed=completed.filter(e=>e.details?.passed===true).length;
  const failed=completed.filter(e=>e.details?.passed===false).length;
  const unknown=completed.length-passed-failed;
  const observationBars=completed.slice(0,20).map(e=>
   '<span class="verification-tick '+(e.details?.passed===true?"is-passed":e.details?.passed===false?"is-failed":"is-pending")+'"></span>').join("");
  page.innerHTML=lead("Overview","Inspect model migration outcomes and recorded execution.")+
   '<section class="workspace-start workspace-start--visual" aria-label="Try Refit live">'+
   '<div class="workspace-start-copy"><h2>Bring your agent. Run a real migration.</h2>'+
   '<p>No account required. Import a GitHub repository or ZIP, compare models, and inspect the resulting sandbox execution and verification evidence.</p>'+
   '<div class="workspace-start-actions"><button class="btn primary" type="button" data-action="new-agent">'+ico("plus")+' Import your agent '+ico("arrow")+'</button>'+
   '<a class="btn" data-nav href="/app/replay">Watch agent execution '+ico("arrow")+'</a>'+ 
   '</div>'+
   '<p class="small sub">Public repositories and ZIPs supported. Code executes in an isolated Vultr sandbox.</p></div>'+
   illustratedAsset("programs")+'</section>'+
   '<section class="overview-recent" aria-label="Recorded migration">'+
   '<div class="overview-recent-heading"><div class="overview-recent-heading-text"><span class="overview-recent-label">Python knowledge-base agent</span>'+
   '<span class="overview-recent-meta">Recorded evaluation · Read-only sample</span></div>'+statusChip(r.status)+'</div>'+
   '<div class="migration-route" role="group" aria-label="Original model and replacement model">'+
   '<div class="migration-endpoint"><span class="migration-endpoint-label">Original model</span>'+modelIdentity(r.source)+'</div>'+
   '<div class="migration-connector" aria-hidden="true"><svg width="48" height="20" viewBox="0 0 48 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 10h43m-7-6 7 6-7 6"/></svg></div>'+
   '<div class="migration-endpoint"><span class="migration-endpoint-label">Replacement</span>'+modelIdentity(r.target)+'</div></div>'+
   '<div class="verification-strip" aria-label="'+safe(passed+' passed, '+failed+' failed, '+unknown+' not recorded among '+completed.length+' case observations')+'">'+
   '<div class="verification-caption"><span>Observed checks</span><strong>'+safe(passed)+' passed'+(failed?', '+safe(failed)+' failed':'')+'</strong></div>'+
   '<div class="verification-bars" aria-hidden="true">'+observationBars+'</div></div>'+
   '<div class="overview-recent-footer"><span class="overview-footnote">'+safe(modelCalls.length)+' model responses · '+safe(cleanup.length)+' verified cleanups</span>'+
   '<button class="btn" type="button" data-action="run" data-id="'+safe(r.id)+'">Inspect run '+ico("arrow")+'</button></div>'+
   '</section>'+
   '<section class="overview-activity" aria-label="Recorded activity"><div class="overview-activity-head"><h3>Activity</h3>'+
   '<span>'+safe(evidence.length)+' events</span></div>'+
   '<div class="overview-event-list">'+recent.map(e=>{
    const d=e.details||{},verified=d.receipt?.verified===true||d.passed===true;
    const failure=d.passed===false||d.receipt?.verified===false||!!d.error;
    return '<button type="button" class="overview-event" data-action="overview-trace" data-id="'+safe(r.id)+'" data-seq="'+safe(e.seq)+'">'+
     '<span class="overview-event-dot '+(failure?"failed":verified?"passed":"")+'"></span>'+
     '<span class="overview-event-name">'+safe(RefitOutcomes.eventLabel(e.type))+'</span>'+
     '<span class="overview-event-context">'+safe([d.case,d.model,d.phase].filter(Boolean).join(" · ")||"Runtime event")+'</span>'+
     '<time class="overview-event-time">'+safe((e.time||"").slice(11,19))+'</time>'+ico("arrow")+'</button>';
   }).join("")+'</div></section>'+
   '<div class="section-footnote">Recorded example. Import your own agent above to run a new migration.</div>';
  return;
 }
 const capacity=await req("");
 if(!state.projects.length&&!state.runs.length){
  page.innerHTML=lead("Your workspace","Connect an existing agent to begin.")+
   '<section class="workspace-start workspace-start--visual">'+
   '<div class="workspace-start-copy"><h2>Your first migration starts with the source.</h2><p>Connect a GitHub repository or ZIP. Refit detects the runtime before any model request, then gives you a controlled path to evaluation and verified export.</p>'+
   '<div class="workspace-start-actions">'+importButton()+' <a class="btn" href="/docs">Read setup guide '+ico("arrow")+'</a></div>'+
   '<div class="workspace-start-process"><span>Inspect source</span><span aria-hidden="true">→</span><span>Compare models</span><span aria-hidden="true">→</span><span>Review evidence</span></div></div>'+
   illustratedAsset("folders")+'</section>';
  return;
 }
 page.innerHTML=lead("Your workspace","Your agent migrations and recorded outcomes.",importButton())+
 '<div class="workspace-capacity"><span>Daily request capacity</span><strong>'+
 safe(capacity.account_reserved_today)+' / '+safe(capacity.account_daily_allowance)+' reserved</strong><span class="small sub">Shared capacity remaining: '+safe(capacity.global_remaining_today)+' requests</span></div>'+
 '<div class="metrics"><div class="metric"><strong>'+state.projects.length+'</strong><span>Agents</span></div>'+
 '<div class="metric"><strong>'+state.runs.length+'</strong><span>Runs</span></div>'+
 '<div class="metric"><strong>'+state.runs.filter(r=>r.status==="compatible_on_sample"||r.status==="verified_adaptation").length+'</strong><span>Verified results</span></div>'+
 '<div class="metric"><strong>'+state.runs.filter(r=>!ended(r.status)).length+'</strong><span>In progress</span></div></div>'+
 '<section class="card inner dashboard-runs"><div class="between"><h3>Recent migrations</h3><a href="/app/runs" data-nav class="btn compact">View all '+ico("arrow")+'</a></div>'+
 '<div class="run-history">'+runTable(state.runs.slice(0,5))+'</div></section>'+
 "";
}
const shortStatus=status=>({
 compatible_on_sample:"Compatible",verified_adaptation:"Verified repair",source_baseline_insufficient:"Baseline failed",
 export_failed_original_runner_verification:"Export failed",inference_budget_exhausted:"Budget exhausted",
 cancelled:"Cancelled",running:"Running",cancelling:"Cancelling",queued:"Queued",interrupted:"Interrupted",failed:"Failed"
})[status]||statusText[status]||"Unverified";
const compactStatus=status=>{
 const kind=["compatible_on_sample","verified_adaptation"].includes(status)?"good":ended(status)?"bad":"warn";
 return '<span class="run-status '+kind+'"><span class="status-light"></span>'+safe(shortStatus(status))+'</span>';
};
const runTable=(runs,view="")=>runs.length?
 '<div class="run-table-desktop"><table class="table"><thead><tr><th scope="col">Status</th><th scope="col">Run ID</th><th scope="col">Models</th><th scope="col">Started</th><th class="numeric">Duration</th></tr></thead><tbody>'+
 runs.map(r=>'<tr><td>'+compactStatus(r.status)+'</td><td><button class="link-btn mono" data-action="run" data-view="'+safe(view)+'" data-id="'+safe(r.id)+'">'+safe(r.id)+'</button></td><td><div class="model-pair">'+modelIdentity(r.source)+'<span class="model-pair-sep" aria-hidden="true">→</span>'+modelIdentity(r.target)+'</div></td><td class="run-timestamp">'+safe(formatTime(r.started_at))+'</td><td class="numeric">'+safe(formatDuration(r.execution_seconds))+'</td></tr>').join("")+'</tbody></table></div>'+
 '<div class="run-list-mobile" role="list" aria-label="Migration runs">'+runs.map(r=>{
  const kind=["compatible_on_sample","verified_adaptation"].includes(r.status)?"good":ended(r.status)?"bad":"warn";
  return '<article class="run-mobile-item" role="listitem"><div class="run-mobile-head">'+
   '<button type="button" class="run-mobile-link mono" data-action="run" data-view="'+safe(view)+'" data-id="'+safe(r.id)+'">'+safe(r.id)+'</button>'+
   '<span class="run-mobile-status '+kind+'" title="'+safe(statusText[r.status]||r.status||"Unknown")+'">'+safe(shortStatus(r.status))+'</span></div>'+
   '<div class="run-mobile-models">'+modelIdentity(r.source)+'<span class="model-pair-sep" aria-hidden="true">→</span>'+
    modelIdentity(r.target)+'</div>'+
   '<time class="run-mobile-time">'+safe(formatTime(r.started_at))+'</time></article>';
 }).join("")+'</div>':
 empty("No runs yet","Your migrations will appear here. Import an agent to start.",importButton());
function filteredRuns(){
 const query=state.runsQuery.toLowerCase();
 const agent=new URLSearchParams(location.search).get("agent");
 const cutoff=state.runsPeriod==="all"?null:Date.now()-Number(state.runsPeriod)*86_400_000;
 return state.runs.filter(r=>{
  if(agent&&r.import?.id!==agent)return false;
  if(cutoff!==null&&!(Date.parse(r.started_at)>=cutoff))return false;
  const matches=!query||[r.id,r.source,r.target,r.status,r.import?.repository].filter(Boolean).join(" ").toLowerCase().includes(query);
  const ok=state.runsFilter==="all"||
   (state.runsFilter==="verified"&&["compatible_on_sample","verified_adaptation"].includes(r.status))||
   (state.runsFilter==="active"&&!ended(r.status))||
   (state.runsFilter==="attention"&&ended(r.status)&&!["compatible_on_sample","verified_adaptation"].includes(r.status));
  return matches&&ok;
 });
}
function runIndexRows(){
 const items=filteredRuns();
 return items.length?runTable(items):'<div class="run-filter-empty"><strong>No matching runs</strong><p>Try another status or search term.</p></div>';
}
function runFilters(action=""){
 const options=(items,current)=>items.map(([value,label])=>
  '<option value="'+value+'"'+(value===current?' selected':'')+'>'+label+'</option>').join("");
 return '<div class="run-controls"><label class="run-search">'+ico("search")+
  '<input type="search" id="runQuery" aria-label="Search migration runs" placeholder="Search runs or models" value="'+safe(state.runsQuery)+'"></label>'+
  '<label class="run-facet"><span>Started</span><select id="runPeriod" aria-label="Run start period">'+
  options([["all","All time"],["1","Last 24 hours"],["7","Last 7 days"]],state.runsPeriod)+'</select></label>'+
  '<label class="run-facet"><span>Status</span><select id="runStatus" aria-label="Run status">'+
  options([["all","All runs"],["verified","Verified"],["active","In progress"],["attention","Needs attention"]],state.runsFilter)+
  '</select></label>'+action+'</div>';
}
async function agents(){
 header("Agents");
 await refreshWorkspace();
 page.innerHTML=lead("Agents",state.guest?"Inspect the existing example or bring your own agent.":"Your imported application source snapshots and detected runtimes.",importButton())+
 (state.guest?'<section class="agent-record"><div class="agent-record-icon">'+ico("code")+'</div><div class="agent-record-body"><button type="button" class="agent-record-title" data-action="example-agent">Recorded Python agent</button><p>Knowledge-base application · Verified on Vultr</p><div class="agent-record-meta"><span>Python</span><span>gVisor execution</span>'+compactStatus(state.demo.run.status)+'</div></div><div class="agent-record-actions"><button class="btn agent-record-review" data-action="run" data-id="demo-python-2026-11-07">Review run '+ico("arrow")+'</button></div></section>':"")+
 (state.guest?"":state.projects.length?
 '<label class="run-search agent-search">'+ico("search")+'<input type="search" id="agentQuery" aria-label="Search agents" placeholder="Search repositories or runtimes"></label>'+
 '<div class="card agent-list"><table class="table"><thead><tr><th>Source</th><th>Runtime</th><th>Integration</th><th>Provider boundary</th><th></th></tr></thead><tbody>'+
 state.projects.map(p=>'<tr data-agent-row><td><button class="link-btn" data-action="project" data-id="'+safe(p.id)+'">'+safe(p.repository||"Uploaded ZIP")+'</button><div class="small muted mono">'+safe(p.revision||p.id)+'</div></td><td>'+safe([p.discovery?.framework,p.discovery?.runtime].filter(Boolean).join(" · ")||"Unknown")+'</td><td>'+
 safe(p.discovery?.service_entries?.length?"Service connector required":p.discovery?.entry?"Managed · confirm checks":"Configuration required")+
 '</td><td>'+safe(p.discovery?.provider||"Unconfirmed")+'</td><td><button type="button" data-action="project" data-id="'+safe(p.id)+'" class="btn compact">Inspect source</button> <a data-nav class="btn compact" href="/app/runs?agent='+encodeURIComponent(p.id)+'">Runs</a> <button data-action="remove" data-id="'+safe(p.id)+'" class="btn compact danger">Remove</button></td></tr>').join("")+'</tbody></table><p id="agentNoMatches" class="run-filter-empty" hidden>No matching agents.</p></div>':
 empty("No agents imported","Import a pinned GitHub revision or a ZIP. Refit will inspect the source before any paid execution.",importButton()));
}
async function runs(){
 header("Runs");
 await refreshWorkspace();
 page.innerHTML=lead("Runs","Inspect executions, outcomes and model evidence.")+
 runFilters(state.guest?"":importButton())+'<section class="records" id="runRecords">'+runIndexRows()+'</section>'+
 (state.guest?'<p class="section-footnote"><button class="btn compact" data-action="new-agent">Import your agent</button> to run your own evaluation.</p>':"");
}
async function evidenceIndex(){
 header("Evidence");
 await refreshWorkspace();
 page.innerHTML=lead("Evidence","Review model observations alongside their source execution.")+
 (state.runs.length?'<section class="evidence-collection" aria-label="Investigations">'+
 state.runs.map(r=>
  '<button type="button" class="evidence-collection-row" data-action="run" data-view="evidence" data-id="'+safe(r.id)+'">'+
  '<span class="evidence-collection-symbol">'+ico("pulse")+'</span>'+
  '<span class="evidence-collection-content"><strong class="mono">'+safe(r.id)+'</strong><span class="evidence-collection-models">'+
  modelIdentity(r.source)+'<span class="model-pair-sep" aria-hidden="true">→</span>'+modelIdentity(r.target)+
  '</span></span><span class="evidence-collection-status">'+compactStatus(r.status)+'</span>'+
  '<span class="evidence-collection-arrow">'+ico("arrow")+'</span></button>').join("")+
 '</section>':empty("No evidence yet","Evidence is generated by actual migrations. Nothing is simulated here.",importButton()));
}
async function settings(){
 header("Settings");
 if(state.guest){
   page.innerHTML=guestNote+lead("Settings","Import a GitHub repository or ZIP without an account.")+
   '<section class="card inner" style="max-width:780px"><h3>Open workspace</h3><p style="margin:10px 0 22px">Import a public GitHub project or ZIP and run a model migration in a private, temporary visitor workspace. No account or password.</p><button type="button" class="btn primary" data-action="new-agent">Import agent '+ico("arrow")+'</button></section>';
   return;
 }
 const config=await req("");
 page.innerHTML=lead("Settings","Your developer account and execution limits.")+
 '<div class="card inner" style="max-width:800px"><h3>Account</h3><div class="fact"><span>'+ico("lock")+'</span><span class="sub">Signed in as</span><strong>'+safe(state.username)+'</strong></div><div class="fact"><span>'+ico("shield")+'</span><span class="sub">Isolation</span><strong>Owner-scoped projects and runs</strong></div><div class="fact"><span>'+ico("clock")+'</span><span class="sub">Per-run limit</span><strong>'+safe(config.max_requests)+' requests</strong></div><div class="fact"><span>'+ico("clock")+'</span><span class="sub">Daily allowance</span><strong>'+safe(config.account_reserved_today)+' / '+safe(config.account_daily_allowance)+' reserved</strong></div><div class="fact"><span>'+ico("box")+'</span><span class="sub">Worker</span><strong>Isolated gVisor execution</strong></div><p class="small" style="margin:18px 0">Releases, limits and supported runtimes are documented publicly. Live execution requires explicit authorization and is subject to a shared global ceiling.</p><button class="btn" data-action="signout">Sign out</button></div>';
}
function wizardIntro(){
 return '<div class="import-header import-header--illustrated"><div><h1>Bring your agent</h1><p>Start with the code you already have. We’ll inspect the agent before changing anything.</p></div>'+illustratedAsset("programs")+'</div>';
}
const importPathSteps="";
function caseFields(item={},split="train",removable=false,open=false){
 const value=key=>safe(item[key]||"");
 return '<details class="setup-case" '+(open?"open":"")+'><summary>'+safe(item.split||split)+(item.name?" · "+safe(item.name):"")+'</summary><div class="setup-case-body">'+
 '<input type="hidden" data-case="split" value="'+safe(item.split||split)+'">'+
 '<label class="field">Case name<input class="control" data-case="name" placeholder="lookup-order" value="'+value("name")+'"></label>'+
 '<label class="field">Agent input<textarea class="control" data-case="prompt" rows="2">'+value("prompt")+'</textarea></label>'+
 '<label class="field">Expected output<textarea class="control" data-case="stdout" rows="2">'+value("stdout")+'</textarea></label>'+
 '<details class="case-options" '+(item.json_contains||item.tool?"open":"")+'><summary>Structured output and tools</summary>'+
 '<label class="field">Expected JSON fields<textarea class="control" data-case="json_contains" rows="2">'+safe(item.json_contains?JSON.stringify(item.json_contains):"")+'</textarea></label>'+
 '<label class="field">Required tool<input class="control" data-case="tool" value="'+value("tool")+'"></label>'+
 '<label class="field">Expected tool arguments (JSON object)<textarea class="control" data-case="tool_arguments" rows="2">'+safe(item.tool_arguments?JSON.stringify(item.tool_arguments):"")+'</textarea></label>'+
 '<label class="field">Expected tool result<input class="control" data-case="tool_result" value="'+value("tool_result")+'"></label>'+
 '<label class="field">Forbidden tools, one per line<textarea class="control" data-case="forbidden_tools" rows="2">'+safe((item.forbidden_tools||[]).join("\n"))+'</textarea></label>'+
 '</details><details class="case-options"><summary>Application state checks</summary>'+
 '<label class="field">File assertions (JSON array)<span class="hint">Check existence, change or JSON fields in the sandbox workspace.</span><textarea class="control" data-case="state" rows="2" placeholder="[{&quot;path&quot;:&quot;state.json&quot;,&quot;op&quot;:&quot;changed&quot;}]">'+safe(item.state?JSON.stringify(item.state):"")+'</textarea></label>'+
 '</details>'+(removable?'<button class="btn" type="button" data-action="remove-case">Remove case</button>':'')+'</div></details>';
}
function selectedDiscovery(){
 const discovery=state.wizard.project.discovery||{};
 return {...discovery,...state.wizard.application};
}
function setupFields(discovery){
 const stored=state.wizard.setup;
 let config={};
 try{config=JSON.parse(stored||"{}")||{};}catch{}
 const node=discovery.runtime==="typescript";
 const field=node?"entry":"module";
 const suggested=(discovery.entry||"").replace(/^python -m /,"");
 const selected=config[field]||(node||discovery.entry?.startsWith("python -m ")?suggested:"");
 const items=Array.isArray(config.cases)&&config.cases.length?config.cases:["train","validation","holdout"].map(split=>({split}));
 const advanced=state.wizard.advanced===true;
 return '<section class="setup-fields"><div class="between setup-heading"><div><h3>Application contract</h3><p class="hint">Confirm the original invocation and define the behaviors that must pass.</p></div>'+
 '<button class="btn" type="button" data-action="toggle-setup">'+(advanced?"Use guided setup":"Edit JSON")+'</button></div>'+
 (advanced?'':'<div id="guidedSetup">'+
 '<label class="field">'+(node?"Node entry file":"Python module")+'<input id="entryPoint" class="control" value="'+safe(selected)+'"></label>'+
 '<label class="field">Command arguments, one per line<span class="hint">Use {prompt} for the case input and {model} if your CLI accepts a model argument.</span><textarea id="runtimeArgs" class="control" rows="2">'+safe((config.args||["{prompt}"]).join("\n"))+'</textarea></label>'+
 '<label class="field">Provider environment variables<span class="hint">Choose the variable names the original agent reads. Both use non-streaming Chat Completions.</span><select id="providerEnv" class="control">'+
 '<option value="openai">OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL</option>'+
 '<option value="generic" '+(config.provider_env==="generic"?"selected":"")+'>BASE_URL, API_KEY, MODEL</option></select></label>'+
 '<h3>Evaluation cases</h3><p class="hint">Use different inputs for training, validation and holdout. Expected outcomes stay outside the agent container.</p>'+
 '<div id="caseFields">'+items.map((item,index)=>caseFields(item,item.split,index>=3,index===0)).join("")+'</div>'+
 '<div class="hstack"><label class="field">Additional case split<select id="extraSplit" class="control"><option>train</option><option>validation</option><option>holdout</option></select></label><button class="btn" type="button" data-action="add-case">Add case</button></div>'+
 '<details class="case-options" '+(config.instruction_env?"open":"")+'><summary>Permit instruction adaptation</summary>'+
 '<label class="field">Existing instruction environment variable<input id="instructionEnv" class="control" value="'+safe(config.instruction_env||"")+'"></label>'+
 '<label class="field">Original instructions<textarea id="instructionBase" class="control" rows="3">'+safe(config.instruction_base||"")+'</textarea></label></details></div>')+
 '<label id="advancedSetup" class="field" '+(!advanced?"hidden":"")+'>Application contract JSON<textarea id="setup" class="control" spellcheck="false" rows="10">'+safe(stored||"")+'</textarea></label></section>';
}
function readSetup(discovery){
 if(state.wizard.advanced){
  try{return JSON.parse(el("setup").value);}catch{throw Error("Enter valid application contract JSON.");}
 }
 const field=discovery.runtime==="typescript"?"entry":"module";
 const setup={format:"refit.agent.v1",[field]:el("entryPoint").value.trim(),
  args:el("runtimeArgs").value.split("\n"),
  cases:[...el("caseFields").querySelectorAll(".setup-case")].map(group=>{
   const item={};
   for(const input of group.querySelectorAll("[data-case]")){
    const key=input.dataset.case,value=input.value;
    if(!value&&!(["split","name","prompt"].includes(key)))continue;
    if(key==="json_contains"||key==="tool_arguments"||key==="state"){
     try{item[key]=JSON.parse(value);}catch{throw Error("Structured checks, tool arguments and file assertions must be valid JSON.");}
    }else item[key]=key==="forbidden_tools"?value.split("\n").map(x=>x.trim()).filter(Boolean):value;
   }
   return item;
  })};
 if(el("providerEnv").value!=="openai")setup.provider_env=el("providerEnv").value;
 if(el("instructionEnv").value||el("instructionBase").value){
  setup.instruction_env=el("instructionEnv").value.trim();
  setup.instruction_base=el("instructionBase").value;
 }
 return setup;
}
async function flow(){
 let step=state.wizard?.step||0;
 if(!step)header("Import agent",1);
 if(step===1)header("Inspect your agent",1);
 if(step===2)header("Configure migration",2);
 if(step===0){
  page.innerHTML='<div class="import-shell">'+wizardIntro()+
   '<section class="import-panel"><div class="import-panel-header"><div><h2>Where is your agent?</h2><p>Point Refit to the existing source. No code changes yet.</p></div><span class="import-privacy">'+ico("lock")+' Your workspace</span></div>'+
   '<div class="import-tabs" role="group" aria-label="Source type"><button type="button" class="import-tab active" data-import-mode="github" aria-pressed="true">'+ico("git")+' GitHub repository</button><button type="button" class="import-tab" data-import-mode="zip" aria-pressed="false">'+ico("upload")+' Upload ZIP</button></div>'+
   '<form id="importForm"><input type="hidden" id="method" value="github">'+
   '<div class="import-form-body"><div id="githubFields"><label class="field" for="repository">Repository URL</label><div class="import-input-wrap"><span class="import-input-icon">'+ico("git")+'</span><input class="import-primary-input" id="repository" type="url" placeholder="https://github.com/owner/repository" autocomplete="url" spellcheck="false" required></div><p class="import-helper">Refit pins the commit and downloads selected source files. Build output, caches and binary assets are skipped by default.</p></div>'+
   '<div id="zipField" hidden><label class="field" for="zip">Source archive</label><input id="zip" class="control import-file" type="file" accept=".zip,application/zip"><p class="import-helper">Up to 32 MiB compressed. Refit reads eligible files within the 12 MiB source budget.</p></div>'+
   '<details class="import-advanced" id="advancedImport"><summary>Advanced options '+ico("arrow")+'</summary><div class="import-advanced-fields"><label class="field" for="revision">Exact commit SHA <span class="hint">Optional · overrides latest commit</span></label><input class="control mono" id="revision" placeholder="40-character commit hash" maxlength="40" autocomplete="off" spellcheck="false"><label class="field" for="repoToken">Private repository token <span class="hint">Optional · used only for this import</span></label><input type="password" id="repoToken" class="control mono" placeholder="GitHub read token" autocomplete="new-password" spellcheck="false" data-lpignore="true"><label class="field" for="sourceDirectory">Application directory <span class="hint">Optional · relative to repository root</span></label><input class="control mono" id="sourceDirectory" placeholder="apps/support-agent" spellcheck="false"><label class="field" for="sourceFiles">Source file override <span class="hint">Optional · one path per line relative to the application directory</span></label><textarea class="control mono" id="sourceFiles" rows="3" spellcheck="false"></textarea></div></details></div>'+
   '<div class="import-actions"><p>'+ico("shield")+' Inspection is private. No inference at this step.</p><button class="btn primary" type="submit">Inspect agent '+ico("arrow")+'</button></div></form></section>'+
 '<p class="section-footnote">Don’t have an agent ready? <button type="button" class="btn compact" data-action="try-live">Run a live sample instead</button></p>'+importPathSteps+'</div>';
  return;
 }
 const p=state.wizard.project,d=selectedDiscovery();
 if(step===1){
   const service=d.service_entries?.[0];
   const serviceOnly=service&&d.runnable===false;
   const runtime=d.framework?[d.framework,d.runtime,d.node_requirement&&"Node "+d.node_requirement].filter(Boolean).join(" · "):d.runtime;
   const features=[["Agent entry point",d.entry||(serviceOnly?"No managed entry point":"Not confidently detected")],
     ["Runtime",runtime||"Unknown"],["Provider",d.provider||(d.provider_signals?.length?"Configuration signals found below":"Not detected")],
     ["Dependencies",d.dependencies?.length ? d.dependencies.join(", ") : "Not reported"],
     ["Tools",d.tool||"Verify during execution"],["Provider signals",d.provider_signals?.join(", ")||"Not detected"]];
   const files=[...(d.evaluation_inputs||[]),...(d.evaluation_files||[])];
   const serviceGuidance=serviceOnly?'<div class="entry-guidance"><h3>HTTP service detected</h3><p><code>'+
     safe(service.method+" "+service.route)+'</code> in <code>'+safe(service.path)+'</code></p><p>'+
     safe(d.setup)+'</p><a href="https://github.com/Davemafy/refit/blob/main/docs/bring-your-agent.md#developer-side-connectors">Read the connector setup guide</a></div>':"";
   const needsEntry=!d.entry&&d.runnable!==false;
   const entryGuidance=needsEntry?
     '<div class="entry-guidance"><h3>Confirm the agent entry point</h3><p>Refit detected '+
     safe(d.runtime||"a source runtime")+' but could not identify an executable entry. Continue to configuration and provide '+
     (d.runtime==="typescript"?"the Node entry file":"the Python module or original entry point")+
     ' relative to the selected source. '+(d.provider?"":"The model provider is also unconfirmed. ")+
     'Define independent checks before authorizing execution.</p></div>':"";
   page.innerHTML=lead("Inspect your agent",serviceOnly?"Review the service boundary and choose how to connect it.":"Review the detected runtime and confirm the original entry point.")+
   serviceGuidance+'<section class="card"><div class="repo-card-head"><div class="repo-mark">'+ico("git")+'</div><div style="flex:1"><h3>'+safe(p.repository||"Uploaded ZIP")+'</h3><p class="small mono">'+safe(p.revision||p.id)+'</p></div><span class="chip bordered">'+safe(p.file_count)+' files inspected</span></div>'+
   '<div class="split-panel"><div>'+features.map(f=>'<div class="fact"><span class="muted">'+ico(f[0]==="Runtime"?"code":f[0]==="Tools"?"layers":"box")+'</span><strong>'+safe(f[0])+'</strong><span class="value">'+safe(f[1])+'</span></div>').join("")+'</div>'+
   '<div><h3 style="margin-bottom:12px">Evaluation sources</h3><p class="small">Candidate inputs and tests from the repository. Review and select independent checks before authorizing a run.</p><div class="file-list" style="margin-top:14px">'+(files.length?files.map(f=>'<div>'+ico("file")+' '+safe(f)+'</div>').join(""):'<div>No individual test-file paths reported.</div>')+'</div></div></div></section>'+
   (d.applications?.length||d.runtime==="mixed"?'<section class="card inner" style="margin-top:16px"><label class="field" for="applicationBoundary">Application boundary</label>'+
     '<select id="applicationBoundary" class="control"><option value="">'+safe(d.entry||"Choose a runtime or detected entry")+'</option>'+
     (d.applications||[]).map((app,index)=>'<option value="'+index+'" '+(state.wizard.application?.path===app.path?"selected":"")+'>'+safe(app.entry+" · "+app.runtime+" · "+app.confidence+" confidence")+'</option>').join("")+
     '<option value="python">Enter a Python module</option><option value="typescript">Enter a Node entry file</option></select>'+
     '<p class="small" id="boundaryEvidence">'+safe(state.wizard.application?.evidence?.join(" · ")||"Confirm the entry point before configuring an evaluation.")+'</p></section>':'')+
   (p.selection_counts?'<section class="card inner" style="margin-top:16px"><h3>Source selection</h3>'+
     (p.directory?'<p class="small">Scope: <code>'+safe(p.directory)+'</code></p>':'')+
     '<div class="hstack" style="flex-wrap:wrap;margin-top:10px">'+["included","excluded","unsupported"].map(status=>
       '<button type="button" class="btn" data-action="source-report" data-status="'+status+'">'+safe(p.selection_counts[status]||0)+' '+status+'</button>').join("")+
     (p.repository?'<button type="button" class="btn" data-action="adjust-source">Adjust source scope</button>':'')+
     '</div><div id="sourceReport" aria-live="polite"></div>'+
     '<details class="case-options" style="margin-top:12px"><summary>Detected source signals</summary>'+[["Entry candidates",d.entry_candidates],["Imports",d.imports],["Configuration",d.configuration_files]].map(([label,items])=>
       '<p class="small"><strong>'+label+'</strong> '+safe(items?.join(", ")||"None detected")+'</p>').join("")+'</details></section>':'')+
   (d.runnable===false?'<section class="import-recovery" role="note"><h3>This source needs another entry point</h3><p>'+
     safe(d.setup||"Refit could not execute this entry using the supported managed runtimes.")+
     ' Your imported snapshot and recorded runs are preserved. Adjust the source selection or import a different boundary—no deletion required.</p>'+
     '<div class="button-row"><button class="btn primary" type="button" data-action="adjust-source">Adjust source and retry '+ico("arrow")+
     '</button><a class="btn" href="/docs">Supported runtimes</a></div></section>':
     d.setup?'<p class="small sub" style="margin-top:16px">'+safe(d.setup)+'</p>':'')+
   entryGuidance+
   '<div class="flow-footer"><button class="btn" data-action="flow-back">'+ico("back")+' Back</button><button class="btn primary" data-action="flow-config" '+(d.runnable===false?"disabled":"")+'>Continue to configuration '+ico("arrow")+'</button></div>';
   return;
 }
 state.capabilities=state.guest
   ?{models:[state.demo.run.source,state.demo.run.target],max_requests:state.demo.run.budget}
   :await req("");
 const remaining=state.capabilities.max_requests;
 const minimum=state.capabilities.minimum_complete_migration_requests||7;
 const canVerify=remaining>=minimum;
 const budgetValue=canVerify?Math.min(Math.max(Number(state.wizard.budget)||remaining,minimum),remaining):0;
 const models=state.capabilities.models||[];
 const source=state.wizard.source||models[0]||"",target=state.wizard.target||models[1]||"";
 page.innerHTML=lead("Configure migration","Choose the source and replacement models, then supply independent evaluation cases.")+
 '<div class="flow-grid"><section class="card inner stack"><label class="field">Original model <span class="hint">The model used for baseline execution.</span><select class="control" id="source">'+models.map(m=>'<option '+(source===m?"selected":"")+' value="'+safe(m)+'">'+safe(m)+'</option>').join("")+'</select></label>'+
 '<label class="field">Replacement model <span class="hint">The model whose behavior will be verified.</span><select class="control" id="target">'+models.map(m=>'<option '+(target===m?"selected":"")+' value="'+safe(m)+'">'+safe(m)+'</option>').join("")+'</select></label>'+
 (d.preset?'<div class="hint-note">'+safe(d.evaluation||"Reviewed native evaluation preset will be used.")+'</div>':
  setupFields(d))+
 '<label class="field">Maximum Vultr requests<input type="number" id="budget" class="control" min="'+safe(minimum)+'" max="'+safe(remaining)+'" value="'+safe(budgetValue)+'" '+(!canVerify?"disabled":"")+'></label>'+
 (!canVerify?'<p class="hint-note" role="status">'+
   (state.capabilities.review_run_used?'This review link has already submitted its one migration. <a href="/app/runs">Open Runs</a> to inspect the saved evidence and launch its permitted diagnostic.':
    state.capabilities.review_pass_expired?'This review access has expired. The existing run remains accessible through a valid session.':
    'A full evaluation needs at least '+safe(minimum)+' requests. Only '+safe(remaining)+' remain today; your imported agent is saved until the UTC allowance resets.')+
   '</p>':'<p class="small sub">Available now: '+safe(remaining)+' requests · minimum for complete evaluation: '+safe(minimum)+' · shared pool remaining: '+safe(state.capabilities.global_remaining_today??remaining)+'</p>')+
 '<label class="hstack" style="font-size:13px"><input id="authorize" type="checkbox" style="width:17px;height:17px"> I authorize this bounded live inference run.</label></section>'+
 '<aside class="card inner side-facts"><h3>Migration summary</h3><hr><div class="pair-line"><span class="sub">Source</span><span>'+safe(p.repository||"Uploaded ZIP")+'</span></div><div class="pair-line"><span class="sub">Entry point</span><span>'+safe(d.entry||"Operator-configured")+'</span></div><div class="pair-line"><span class="sub">Runtime</span><span>'+safe(d.runtime)+'</span></div><div class="pair-line"><span class="sub">Verification</span><span>Original-runtime fresh check</span></div><div class="hint-note">'+ico("shield")+' Untrusted source runs inside a bounded disposable gVisor container. No production services are enabled by default.</div></aside></div>'+
 '<div class="flow-footer"><button class="btn" data-action="flow-inspect">'+ico("back")+' Back to inspection</button>' +(state.capabilities.review_run_used?'<a class="btn primary" href="/app/runs">Open saved migration '+ico("arrow")+'</a>':'<button id="start" class="btn primary" data-action="start-migration" '+(!canVerify?"disabled":"")+' >Run migration '+ico("arrow")+'</button>')+'</div>';
}
async function importProject(){
 await ensureGuestSession();
 const btn=page.querySelector('#importForm button[type="submit"]');
 if(btn)btn.disabled=true;
 try{
   const kind=el("method").value;let body={method:kind}, endpoint="/imports";
   if(kind==="github"){
     const input=el("repository").value.trim();
     const parsed=input.match(/^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)(?:\/)?$/i);
     if(!parsed)throw Error("Paste a GitHub repository URL like https://github.com/owner/repository.");
     const owner=parsed[1],name=parsed[2].replace(/\.git$/i,"");
     body.repository=owner+"/"+name;
     body.revision=el("revision").value.trim().toLowerCase();
     if(body.revision&&!/^[a-f0-9]{40}$/.test(body.revision))
       throw Error("An exact commit must be a 40-character SHA. Otherwise leave it blank.");
     body.token=el("repoToken").value;
     body.directory=el("sourceDirectory").value.trim();
     const selected=el("sourceFiles").value.split("\n").map(path=>path.trim()).filter(Boolean);
     if(selected.length)body.files=selected;
     el("repoToken").value="";
   }else{
     const file=el("zip").files[0];
     if(!file||!file.size||file.size>32*1024*1024)throw Error("Select a nonempty ZIP no larger than 32 MiB.");
     endpoint="/imports/zip";
     body=file;
   }
   const project=await req(endpoint,body);
   state.wizard={step:1,project,source:null,target:null,setup:"",budget:null};
   await refreshWorkspace();
   await flow();
 }catch(e){notify(e.message);}finally{if(btn?.isConnected)btn.disabled=false;}
}
async function chooseProject(id){
 const item=state.projects.find(p=>p.id===id);
 if(!item)throw Error("This project is no longer in your workspace.");
 state.wizard={step:1,project:item,source:null,target:null,setup:"",budget:null};
 navigate("/app/agents/new");
}
async function startMigration(){
 await ensureGuestSession();
 const btn=el("start");if(btn)btn.disabled=true;
 try{
   const p=state.wizard.project,d=selectedDiscovery();
   const source=el("source").value,target=el("target").value;
   if(source===target)throw Error("Select two different models.");
   if(!el("authorize").checked)throw Error("Authorize the inference budget before starting.");
   state.capabilities=await req("");
   const minimum=state.capabilities.minimum_complete_migration_requests||7;
   if(state.capabilities.max_requests<minimum)throw Error("Not enough inference capacity for one complete evaluation. Your imported agent remains saved.");
   const budget=Number(el("budget").value);
   if(!Number.isInteger(budget)||budget<minimum||budget>state.capabilities.max_requests)throw Error("Choose a request budget of at least "+minimum+" to verify a complete migration.");
   const body={import_id:p.id,source,target,budget,authorize:true};
   if(!d.preset)body.setup=readSetup(d);
   state.wizard.source=source;state.wizard.target=target;state.wizard.budget=budget;
   if(body.setup)state.wizard.setup=JSON.stringify(body.setup,null,2);
   const run=await req("/runs",body);
   navigate("/app/runs/"+run.id);
 }catch(e){notify(e.message);}finally{if(btn?.isConnected)btn.disabled=false;}
}
function renderComparison(cases,source,target,report){
 const rows=RefitOutcomes.pairs({source,target},cases);
 if(!rows.length)return '<p class="comparison-empty">No case comparisons have been recorded yet. Results will appear when the application finishes a case.</p>';
 const repair=!!report?.proposal;
 const checkLabels={stdout_matches:"Exact output",json_matches:"Structured output",
  required_tool_called:"Required tool called",required_tool_observed:"Required tool result",
  forbidden_tools_absent:"Forbidden tools absent",tool_arguments_match:"Required tool arguments",
  state_checks_passed:"Application state"};
 const cell=observation=>{
  const d=observation?.details;
  if(!d)return '<span class="muted">Not recorded</span>';
  const checks=Object.entries(checkLabels).filter(([key])=>typeof d.verdict?.[key]==="boolean");
  const tools=(Array.isArray(d.trace)?d.trace:[]).flatMap(call=>call.tools_called||[]);
  return (d.passed?'<span class="chip good">'+ico("check")+' Passed</span>':
   '<span class="chip bad">'+ico("alert")+' Failed</span>')+
   '<details class="case-options comparison-checks"><summary>View checks</summary><ul>'+
   checks.map(([key,label])=>'<li class="'+(d.verdict[key]?"sub":"error")+'">'+safe(label)+(d.verdict[key]?" passed":" failed")+'</li>').join("")+
   (Array.isArray(d.state_checks)?d.state_checks:[]).map(check=>'<li class="'+(check.passed?"sub":"error")+'">'+
    safe(check.path+" · "+check.op.replaceAll("_"," ")+" · "+(check.before?.status||"unknown")+" → "+(check.after?.status||"unknown")+(check.passed?" · passed":" · failed"))+'</li>').join("")+
   (tools.length?'<li class="sub">Model requested '+safe(tools.join(", "))+'</li>':"")+
   (Number.isInteger(d.model_requests)?'<li class="sub">'+safe(d.model_requests)+' model requests</li>':"")+
   (d.error?'<li class="error">'+safe(d.error.replaceAll("_"," "))+'</li>':"")+'</ul><button type="button" class="evidence-jump" data-action="inspect-evidence" data-key="case-'+safe(observation.seq)+'">Open this observation '+ico("arrow")+'</button></details>';
 };
 return '<div class="comparison-scroll"><table class="table comparison-table"><thead><tr><th scope="col">Case</th><th scope="col">Original · '+modelIdentity(source)+'</th><th scope="col">Replacement · '+modelIdentity(target)+'</th>'+
 (repair?'<th scope="col">Adapted replacement</th>':'')+'<th scope="col">Observed result</th></tr></thead><tbody>'+
 rows.map(row=>{
  const original=row.source?.details,replacement=row.target?.details,adapted=row.adapted?.details;
  const inspection=row.status==="source_failed"?row.source:row.target||row.source;
  const description=row.status==="regression"?"Replacement failed required checks":
   row.status==="source_failed"?"Original baseline failed":
   row.status==="both_passed"?(row.identicalOutput?"Both passed · same output":"Both passed · outputs differ"):
   row.status==="target_failed"?"Replacement checks failed":"Awaiting both results";
  return '<tr class="'+(["regression","source_failed","target_failed"].includes(row.status)?"comparison-failed":"")+'"><td>'+
   '<strong>'+safe(row.name)+'</strong><span class="comparison-phase">'+safe(RefitOutcomes.phaseName(row.phase))+'</span></td>'+
   '<td>'+cell(row.source)+'</td><td>'+cell(row.target)+'</td>'+(repair?'<td>'+cell(row.adapted)+'</td>':'')+
   '<td><span class="comparison-result '+(["regression","source_failed","target_failed"].includes(row.status)?"is-failed":"")+'">'+safe(description)+'</span>'+
   (inspection?'<button class="evidence-jump" type="button" data-action="inspect-evidence" data-key="case-'+safe(inspection.seq)+'">Inspect evidence '+ico("arrow")+'</button>':'')+'</td></tr>';
 }).join("")+'</tbody></table></div>'+
 '<div class="comparison-mobile">'+rows.map(row=>{
  const inspection=row.status==="source_failed"?row.source:row.target||row.source;
  const status=row.status==="both_passed"?"Both models passed":
   row.status==="regression"?"Replacement regression":
   row.status==="source_failed"?"Original baseline failed":
   row.status==="target_failed"?"Replacement checks failed":"Awaiting comparison";
  const outcome=(name,model,item)=>'<div class="comparison-mobile-result"><div><span>'+safe(name)+'</span>'+
   '<small class="mono">'+modelIdentity(model)+'</small></div>'+cell(item)+'</div>';
  return '<section class="comparison-mobile-case"><div class="comparison-mobile-head"><div><strong>'+
   safe(row.name)+'</strong><span>'+safe(RefitOutcomes.phaseName(row.phase))+'</span></div>'+
   '<span class="comparison-mobile-verdict '+(row.status==="both_passed"?"is-good":"")+'">'+safe(status)+'</span></div>'+
   outcome("Original",source,row.source)+outcome("Replacement",target,row.target)+
   (repair?outcome("Adapted replacement",target,row.adapted):"")+
   (inspection?'<button type="button" class="evidence-jump" data-action="inspect-evidence" data-key="case-'+
    safe(inspection.seq)+'">Inspect the observation '+ico("arrow")+'</button>':"")+'</section>';
 }).join("")+'</div>';
}

// Evidence navigation only exposes observations returned by the run API.
function evidenceEntries(run,events){
 const entries=[];
 (run.verification||[]).forEach((details,index)=>entries.push({
  key:"verification-"+index,type:"verification",title:details.case||"Verification "+(index+1),
  subtitle:"Fresh export check",details
 }));
 events.filter(event=>event.type==="case_completed").forEach(event=>entries.push({
  key:"case-"+event.seq,type:"case",title:event.details?.case||"Case "+event.seq,
  subtitle:[event.details?.phase,event.details?.model].filter(Boolean).join(" · "),
  details:event.details||{}
 }));
 events.filter(event=>event.type==="sandbox_cleanup").forEach(event=>entries.push({
  key:"cleanup-"+event.seq,type:"cleanup",
  title:event.details?.case||"Sandbox "+event.seq,
  subtitle:[event.details?.phase,"Cleanup receipt"].filter(Boolean).join(" · "),
  details:event.details||{}
 }));
 if(run.diagnostic)entries.push({
  key:"diagnostic",type:"diagnostic",title:"Generated diagnostic",
  subtitle:"Vultr-generated Python · isolated execution",details:run.diagnostic
 });
 if(run.containment)entries.push({
  key:"containment",type:"containment",title:"Host containment test",
  subtitle:"Separate synthetic probe · observed on Vultr",details:run.containment
 });
 entries.push({key:"provenance",type:"provenance",title:"Run provenance",
  subtitle:"Configuration and run identifiers",details:run});
 return entries;
}
function evidenceOutcome(item){
 const d=item.details;
 if(item.type==="case"||item.type==="verification")
  return typeof d.passed==="boolean"?(d.passed?"Passed":"Failed"):"Not recorded";
 if(item.type==="cleanup")
  return d.receipt?.verified===true?"Verified":d.receipt?.verified===false?"Unverified":"Not recorded";
 if(item.type==="diagnostic")
  return d.status==="verified"?"Verified":d.status==="running"?"Executing":d.status==="rejected"?"Not verified":d.status||"Not recorded";
 if(item.type==="containment")return d.verified===true?"Verified":"Not verified";
 return "Recorded";
}
function evidenceDetail(item){
 const d=item.details;
 const field=(label,value)=>'<div class="evidence-field"><dt>'+safe(label)+'</dt><dd>'+safe(value===undefined||value===null||value===""?"Not recorded":value)+'</dd></div>';
 const fields=[];
 let supplemental="";
 if(item.type==="provenance"){
  fields.push(field("Run ID",d.id),field("Status",d.status),
   field("Source model",d.source),field("Replacement model",d.target),
   field("Started",d.started_at),field("Finished",d.finished_at),
   field("Configuration SHA-256",d.configuration_sha256),
   field("Model requests",d.model_requests),field("Inference budget",d.budget),
   field("Verified export",d.export_available===true?"Available":"Not available"));
 }else if(item.type==="cleanup"){
  fields.push(field("Case",d.case),field("Phase",d.phase),
   field("Receipt verified",d.receipt?.verified===true?"Yes":d.receipt?.verified===false?"No":"Not recorded"),
   field("Cleanup reason",d.receipt?.reason),field("Observed",d.receipt?.observed_at),
   field("Container",d.receipt?.container_name||d.container));
 }else if(item.type==="containment"){
  fields.push(field("Vultr deployment SHA",d.revision),
   field("Execution origin","Vultr VM · separately operator initiated"),
   field("Evidence type","Synthetic containment test (not model-generated)"),
   field("Host canary intact",d.host_canary_unchanged===true?"Verified":"Not verified"),
   field("Probe status",d.verified===true?"Verified":"Not verified"));
  (d.workers||[]).forEach(worker=>{
    fields.push(field(worker.kind+" runtime",worker.runtime),
      field(worker.kind+" process",worker.status),
      field(worker.kind+" cleanup",worker.cleanup_verified===true?"Verified":"Not verified"),
      field(worker.kind+" ledger",worker.ledger_valid===true?"Valid":"Not verified"));
  });
  supplemental='<h4>Prohibited actions observed</h4><div class="evidence-checks">'+
    (d.attempts||[]).map(attempt=>
      '<div><span class="'+(attempt.blocked?"sub":"error")+'">'+
       safe(attempt.blocked?"Contained":"Unverified")+'</span><span>'+
       safe(attempt.action)+' · '+safe(attempt.observed)+'</span></div>').join("")+
    '</div><p class="small sub">This is a separate controlled host test. The model-generated diagnostic and its unseen-input check are documented above.</p>';
 }else if(item.type==="diagnostic"){
  const worker=d.sandbox||{},policy=worker.policy||worker.ledger?.[0]?.event?.policy||{};
  const challenge=d.cross_check||{},second=challenge.sandbox||{};
  fields.push(field("Migration run",d.migration_id),
   field("Vultr model",d.generator_model),field("Model requests",d.model_requests),
   field("Scope",d.scope||"Measured training only"),
   field("Diagnostic verification",d.verified===true?"Passed":"Not verified"),
   field("Execution",worker.status),field("Sandbox runtime",worker.runtime),
   field("Container created",worker.container_created===true?"Yes":"No"),
   field("Exit code",worker.exit_code),
   field("Wall time (ms)",worker.duration_ms),
   field("Code digest",worker.code_sha256),
   field("Network",policy.network),field("Memory limit (MB)",policy.memory_mb),
   field("CPU limit",policy.cpus),field("PID limit",policy.pids_limit),
   field("Runtime binary",worker.runtime_identity?.registered_binary),
   field("Primary cleanup",worker.container_removed_verified===true?"Verified":"Not verified"),
   field("Independent test",second.status),
   field("Independent cleanup",second.container_removed_verified===true?"Verified":"Not verified"),
   field("Ledger",worker.ledger_valid===true?"Hash chain valid":"Not verified"));
  supplemental='<p class="small sub">This diagnostic analyzes observed training scores; it does not determine business safety or unlock an export.</p>'+
   (d.generated_code?'<h4>Vultr-generated Python</h4><pre class="log">'+safe(d.generated_code)+'</pre>':"")+
   (worker.stdout?'<h4>Observed stdout</h4><pre class="log">'+safe(worker.stdout)+'</pre>':"")+
   (worker.stderr?'<h4>Observed stderr</h4><pre class="log">'+safe(worker.stderr)+'</pre>':"")+
   (d.expected?'<h4>Independent verifier expected</h4><pre class="log">'+safe(JSON.stringify(d.expected,null,2))+'</pre>':"")+
   (d.observed?'<h4>Observed parsed output</h4><pre class="log">'+safe(JSON.stringify(d.observed,null,2))+'</pre>':"")+
   (challenge.expected?'<h4>Hidden synthetic cross-check</h4><p class="small sub">The coding model did not see these values before execution.</p><pre class="log">'+
    safe(JSON.stringify({expected:challenge.expected,observed:challenge.observed},null,2))+'</pre>':"")+
   (second.stderr?'<h4>Cross-check stderr</h4><pre class="log">'+safe(second.stderr)+'</pre>':"")+
   (d.validation_error||d.error?'<div class="notice">'+safe(d.validation_error||d.error)+'</div>':"");
 }else{
  fields.push(field("Case",d.case),field("Evaluation",item.type==="verification"?"Fresh export check":d.phase),
   field("Model",d.model),
   field("Outcome",evidenceOutcome(item)),field("Model requests",d.model_requests),
   field("Exit code",d.exit_code),field("Output SHA-256",d.stdout_sha256));
 }
 if(item.type==="case"||item.type==="verification"){
  const verdict=Object.entries(d.verdict||{}).filter(([,value])=>typeof value==="boolean");
  supplemental+=(verdict.length?'<h4>Assertions</h4><div class="evidence-checks">'+verdict.map(([name,passed])=>
   '<div><span class="'+(passed?"sub":"error")+'">'+safe(passed?"Passed":"Failed")+'</span><span>'+
   safe(name.replaceAll("_"," "))+'</span></div>').join("")+'</div>':"");
  const calls=(d.trace||[]).flatMap(trace=>(trace.tools_called||[]).map(name=>({name,trace})));
  supplemental+='<h4>Tool observations</h4>'+(calls.length?
   '<ul class="evidence-tools">'+calls.map(({name,trace})=>'<li><span class="mono">'+safe(name)+'</span><span class="muted small">model request '+safe(trace.number)+'</span></li>').join("")+'</ul>':
   '<p class="small sub">No tool calls recorded for this evaluation.</p>');
  if(d.error)supplemental+='<div class="notice">'+safe(d.error)+'</div>';
 }
 return '<div class="evidence-detail-head"><div><h3>'+safe(item.title)+'</h3><p class="small">'+
   safe(item.subtitle)+'</p></div><span class="chip bordered">'+safe(evidenceOutcome(item))+'</span></div>'+
  '<dl class="evidence-fields">'+fields.join("")+'</dl>'+supplemental;
}
function evidenceExplorer(run,events){
 const entries=evidenceEntries(run,events);
 state.evidenceItems=entries;
 if(!entries.some(item=>item.key===state.evidenceSelected))state.evidenceSelected=entries[0].key;
 const selected=entries.find(item=>item.key===state.evidenceSelected);
 let group="";
 const navigation=entries.map(item=>{
  const section=item.type==="verification"?"Verification":item.type==="case"?"Evaluations":
   item.type==="cleanup"?"Sandbox cleanup":item.type==="diagnostic"?"Generated diagnostics":
   item.type==="containment"?"Containment evidence":"Provenance";
  const heading=section===group?"":'<div class="evidence-group">'+safe(section)+'</div>';
  group=section;
  return heading+'<button type="button" class="evidence-entry'+(item.key===selected.key?" selected":"")+
   '" data-action="evidence-select" data-key="'+safe(item.key)+'" aria-pressed="'+
   (item.key===selected.key?'true':'false')+'"><span class="evidence-entry-title">'+
   safe(item.title)+'</span><span class="evidence-entry-sub">'+safe(item.subtitle)+
   '</span></button>';
 }).join("");
 return '<div class="evidence-workspace"><nav class="evidence-index" aria-label="Run evidence">'+
  navigation+'</nav><section class="evidence-inspector" id="evidenceInspector" aria-live="polite">'+
  evidenceDetail(selected)+'</section></div>';
}

// One visual narrative, computed from the observed run and its events.
function decisionSurface(run,events){
 const o=RefitOutcomes.summarize(run,events);
 const exportText=o.exportState==="available"?"Verified artifact available":
  o.exportState==="pending"?"Verification pending":"No verified export";
 const activeLabel=o.active&&o.stage.phase?o.stage.phase+" · "+o.stage.event:
  o.stage.event;
 const attention=o.regressions.length?o.regressions:
  o.baselineFailures.length?o.baselineFailures:o.otherFailures;
 const focus=o.focus?
  '<button class="decision-cta" type="button" data-action="inspect-evidence" data-key="'+safe(o.focus.key)+'">'+
  (o.failedCount?"Inspect failing evidence":"Inspect recorded evidence")+ico("arrow")+'</button>':"";
 const count=o.total?o.bothPassed+" / "+o.total:"—";
 const detail=o.total?"Paired cases where both models met the required checks":"No paired cases complete yet";
 const summary=attention.length?
  '<div class="decision-findings"><div class="decision-findings-head"><span>'+safe(attention.length)+
  ' observed case'+(attention.length===1?"":"s")+' needing attention</span><span>Open the underlying evidence</span></div>'+
  attention.slice(0,4).map(row=>{
   const e=row.status==="source_failed"?row.source:row.target||row.source;
   return '<button class="finding" type="button" data-action="inspect-evidence" data-key="case-'+safe(e.seq)+'">'+
    '<span class="finding-sign" aria-hidden="true"></span><span class="finding-name">'+safe(row.name)+'</span>'+
    '<span class="finding-phase">'+safe(RefitOutcomes.phaseName(row.phase))+'</span>'+
    '<span class="finding-reason">'+safe(row.status==="regression"?"Replacement regression":row.status==="source_failed"?"Original baseline failed":"Replacement failed")+'</span>'+
    ico("arrow")+'</button>';
  }).join("")+'</div>':
  '<p class="decision-note">'+(o.kind==="compatible"?"Every recorded comparison met the declared requirements. Review individual assertions and fresh export evidence below.":
  o.kind==="running"?"The interface shows only completed observations. New evidence appears as the run progresses.":
  o.kind==="repaired"?"The backend reports a verified adaptation. Inspect its test evidence and the exact accepted instructions.":
  "Review the recorded checks and execution history before making a migration decision.")+'</p>';
 return '<section class="decision-surface '+safe(o.kind)+'" aria-label="Migration outcome" data-verdict="'+safe(o.kind)+'">'+
 '<div class="decision-main"><div class="decision-state"><span class="decision-light"></span>'+
 safe(o.active?"Live execution":"Migration decision")+'</div><h2>'+safe(o.title)+'</h2><p>'+safe(o.description)+'</p>'+
 '<div class="decision-actions">'+focus+'</div></div>'+
 '<div class="decision-aside"><div class="decision-stat"><span>Observed comparison</span><strong class="mono">'+safe(count)+'</strong><small>'+safe(detail)+'</small></div>'+
 '<div class="decision-meta"><span>Latest recorded activity</span><strong>'+safe(activeLabel)+'</strong>'+
 (o.stage.case?'<small>Case: '+safe(o.stage.case)+'</small>':'')+'</div>'+
 '<div class="decision-meta"><span>Export gate</span><strong>'+safe(exportText)+'</strong></div>'+
 '<div class="decision-meta"><span>Sandbox cleanup receipts</span><strong>'+safe(o.cleanupCount?o.cleaned+" / "+o.cleanupCount:"Not recorded")+'</strong></div></div></section>'+summary;
}
function recentRunEvents(events,active){
 const items=events.slice(-6).reverse();
 return '<section class="card inner run-activity"><div class="between"><h3>Execution activity</h3>'+
 (active?'<span class="live-indicator"><span></span>Live</span>':
  '<span class="muted small">'+safe(events.length)+' events</span>')+'</div>'+
 (items.length?'<ol class="activity-entries">'+items.map(e=>{
  const d=e.details||{},when=e.time?e.time.slice(11,19):"";
  return '<li><span class="activity-point"></span><div><strong>'+safe(RefitOutcomes.eventLabel(e.type))+'</strong>'+
   '<span>'+safe([d.phase,d.case,d.model].filter(Boolean).join(" · ")||"Recorded by the runtime")+'</span></div>'+
   '<time class="mono">'+safe(when)+'</time></li>';
 }).join("")+'</ol>':'<p class="small sub" style="margin-top:15px">Waiting for recorded execution events.</p>')+'</section>';
}
function snapshotRunView(){
 const details={};
 document.querySelectorAll(".comparison-checks").forEach((d,i)=>{if(d.open)details[i]=true});
 const entry=document.querySelector(".evidence-index"),inspector=document.querySelector(".evidence-inspector"),log=document.querySelector(".log");
 return {scrollX:window.scrollX,scrollY:window.scrollY,details,
  mainScroll:document.querySelector(".main")?.scrollTop||0,
  traceScroll:document.querySelector(".trace-events")?.scrollTop||0,
  traceInspectorScroll:document.querySelector(".trace-inspector")?.scrollTop||0,
  evidenceScroll:entry?.scrollTop||0,inspectorScroll:inspector?.scrollTop||0,logScroll:log?.scrollTop||0,
  activeId:document.activeElement?.id||null};
}
function restoreRunView(view){
 if(!view)return;
 document.querySelectorAll(".comparison-checks").forEach((d,i)=>{if(view.details[i])d.open=true});
 const entry=document.querySelector(".evidence-index"),inspector=document.querySelector(".evidence-inspector"),log=document.querySelector(".log");
 if(entry)entry.scrollTop=view.evidenceScroll;
 if(inspector)inspector.scrollTop=view.inspectorScroll;
 if(log)log.scrollTop=view.logScroll;
 const main=document.querySelector(".main"),trace=document.querySelector(".trace-events"),
  traceInspector=document.querySelector(".trace-inspector");
 if(main)main.scrollTop=view.mainScroll||0;
 if(trace)trace.scrollTop=view.traceScroll||0;
 if(traceInspector)traceInspector.scrollTop=view.traceInspectorScroll||0;
 window.scrollTo(view.scrollX,view.scrollY);
}

// Recorded event times and run durations drive these diagrams; no simulated spans.
function traceElapsed(events){
 const times=events.map(e=>Date.parse(e.time||"")).filter(Number.isFinite);
 const first=times.length?Math.min(...times):0;
 const last=times.length?Math.max(...times):first;
 return {first,last,total:Math.max(last-first,1)};
}
function traceWaterfall(events){
 const timed=e=>Number.isFinite(Date.parse(e.time||""));
 const caseRecords=events.filter(e=>e.type==="case_completed"&&
  Number.isFinite(Number(e.details?.elapsed_seconds))&&Number(e.details?.elapsed_seconds)>0 &&timed(e));
 // Public examples intentionally omit sandbox-case timing. Their model response
 // durations remain recorded, so show those instead of inventing case spans.
 const usingCases=caseRecords.length>0;
 const modelRecords=usingCases?[]:events.filter(e=>e.type==="inference_completed"&&
  Number.isFinite(Number(e.details?.seconds))&&Number(e.details?.seconds)>0 &&timed(e));
 const records=(usingCases?caseRecords:modelRecords).slice(-18);
 if(!records.length)return '<p class="trace-no-timing">No measured execution durations have been recorded. Select an event below to inspect its observations.</p>';
 const time=traceElapsed(events);
 const heading=usingCases?"Case execution timeline":"Model response timeline";
 const caption=usingCases?"Measured elapsed time":"Recorded model latency";
 return '<div class="trace-overview"><div class="trace-overview-head"><strong>'+heading+'</strong>'+
  '<span>'+caption+' · '+records.length+' '+(usingCases?(records.length===1?"case":"cases"):(records.length===1?"response":"responses"))+'</span></div>'+
  '<div class="trace-waterfall-scroll"><div class="trace-waterfall"><div class="trace-ruler"><span></span>'+
   '<span>0 s</span><span>'+safe((time.total/1000).toFixed(1))+' s</span></div>'+
  records.map(e=>{
   const d=e.details||{},duration=Number(usingCases?d.elapsed_seconds:d.seconds)*1000,end=Date.parse(e.time);
   const left=Math.max(0,Math.min(100,100*(end-duration-time.first)/time.total));
   const width=Math.max(.7,Math.min(100-left,100*duration/time.total));
   const outcome=d.passed===true?"passed":d.passed===false?"failed":"";
   const label=usingCases?(d.case||"Case"):"Request "+(d.number??e.seq);
   return '<button type="button" class="trace-lane" data-action="trace-select" data-seq="'+safe(e.seq)+
    '" aria-label="'+safe(label+" · "+(d.model||"model")+" · "+(duration/1000).toFixed(1)+" seconds")+'">'+
    '<span class="trace-lane-title"><span>'+safe(label)+'</span><small>'+safe(d.model||"Unknown model")+'</small></span>'+
    '<span class="trace-lane-track"><span class="trace-duration-bar '+outcome+
    '" style="left:'+left.toFixed(2)+'%;width:'+width.toFixed(2)+'%"></span></span>'+
    '<span class="trace-lane-time mono">'+safe((duration/1000).toFixed(1))+'s</span></button>';
  }).join("")+'</div></div></div>';
}

const traceGroups={
 all:()=>true,models:e=>e.type==="inference_requested"||e.type==="inference_completed",
 cases:e=>e.type==="case_completed",sandbox:e=>e.type.startsWith("sandbox_")
};
function traceDetails(e){
 if(!e)return '<div class="trace-nothing">Select a recorded event to inspect its details.</div>';
 const d=e.details||{};
 const line=(label,value)=>'<div class="trace-field"><dt>'+safe(label)+'</dt><dd>'+safe(value===null||value===undefined||value===""?"Not recorded":value)+'</dd></div>';
 const fields=[
  line("Sequence",e.seq),line("Recorded time",(e.time||"").slice(11,19)+" UTC"),
  line("Phase",d.phase),line("Case",d.case),line("Model",d.model)
 ];
 if(typeof d.passed==="boolean")fields.push(line("Outcome",d.passed?"Passed":"Failed"));
 if(Number.isFinite(d.seconds))fields.push(line("Model duration",d.seconds+" s"));
 if(Number.isFinite(d.elapsed_seconds))fields.push(line("Case duration",d.elapsed_seconds+" s"));
 if(Number.isInteger(d.model_requests))fields.push(line("Model requests",d.model_requests));
 if(d.receipt)fields.push(line("Sandbox cleanup",d.receipt.verified===true?"Verified":d.receipt.verified===false?"Unverified":"Not recorded"),
  line("Cleanup reason",d.receipt.reason),line("Container",d.receipt.container_name));
 const tools=[...(Array.isArray(d.tools_called)?d.tools_called:[]),
  ...(Array.isArray(d.trace)?d.trace.flatMap(t=>Array.isArray(t.tools_called)?t.tools_called:[]):[])];
 const unique=[...new Set(tools)];
 let extra=unique.length?'<h4>Observed tool calls</h4><div class="trace-tools">'+unique.map(t=>
  '<code>'+safe(t)+'</code>').join("")+'</div>':"";
 const checks=Object.entries(d.verdict||{}).filter(([,v])=>typeof v==="boolean");
 if(checks.length)extra+='<h4>Evaluation checks</h4><div class="trace-checks">'+checks.map(([key,value])=>
  '<span class="'+(value?"passed":"failed")+'">'+safe(key.replaceAll("_"," "))+
  ' · '+(value?"passed":"failed")+'</span>').join("")+'</div>';
 if(d.state_checks?.length)extra+='<h4>Verified application state</h4><ul class="trace-state">'+
  d.state_checks.map(check=>'<li><code>'+safe(check.path)+'</code><span>'+
   safe((check.before?.status||"unknown")+" → "+(check.after?.status||"unknown"))+'</span><strong class="'+
   (check.passed?"passed":"failed")+'">'+(check.passed?"Passed":"Failed")+'</strong></li>').join("")+'</ul>';
 if(d.error)extra+='<div class="notice">'+safe(String(d.error))+'</div>';
 return '<div class="trace-detail-head"><div><span class="trace-sequence mono">Event '+safe(e.seq)+'</span>'+
  '<h3>'+safe(RefitOutcomes.eventLabel(e.type))+'</h3></div></div>'+
  '<dl class="trace-details">'+fields.join("")+'</dl>'+extra+
  '<details class="trace-raw"><summary>Original event payload</summary>'+
  '<pre class="log">'+safe(JSON.stringify({seq:e.seq,type:e.type,time:e.time,details:d},null,2))+'</pre></details>';
}
function traceExplorer(events){
 state.traceEvents=events;
 const filter=traceGroups[state.traceFilter]||traceGroups.all;
 const matches=events.filter(filter),visible=matches.slice(-150);
 const allowed=new Set(visible.map(e=>e.seq));
 if(!visible.some(e=>String(e.seq)===String(state.traceSelected)))
  state.traceSelected=visible.at(-1)?.seq??null;
 const selected=visible.find(e=>String(e.seq)===String(state.traceSelected));
 const filterButtons=[["all","All events"],["models","Model calls"],["cases","Cases"],["sandbox","Sandboxes"]]
  .map(([name,label])=>'<button type="button" class="trace-filter'+(name===state.traceFilter?" selected":"")+
   '" data-action="trace-filter" data-filter="'+name+'" aria-pressed="'+(name===state.traceFilter)+'">'+label+'</button>').join("");
 const groups=[];
 let group=null, currentCase=null;
 for(const e of events){
  const d=e.details||{};
  if(e.type==="phase_started"||!group){
   group={seq:e.seq,label:e.type==="phase_started"?RefitOutcomes.phaseName(d.phase):"Run activity", model:d.model,items:[]};
   groups.push(group);
   currentCase=null;
  }
  if((e.type==="sandbox_starting"||e.type==="sandbox_started"||e.type==="local_started")&&d.case&&currentCase?.name!==d.case){
   currentCase={seq:e.seq,name:d.case,entries:[]};
   group.items.push(currentCase);
  }
  if(allowed.has(e.seq)){
   if(currentCase)currentCase.entries.push(e);
   else group.items.push(e);
  }
  if(e.type==="case_completed")currentCase=null;
 }
 const entry=e=>{
  const d=e.details||{},passed=d.passed===true||d.receipt?.verified===true;
  const failed=d.passed===false||d.receipt?.verified===false||!!d.error;
  const chosen=String(e.seq)===String(state.traceSelected);
  const duration=d.elapsed_seconds??d.seconds;
  return '<button type="button" class="trace-entry'+(chosen?" selected":"")+
   '" data-action="trace-select" data-seq="'+safe(e.seq)+'" aria-pressed="'+chosen+'">'+
   '<span class="trace-event-dot '+(failed?"failed":passed?"passed":"")+'"></span>'+
   '<span class="trace-entry-copy"><strong>'+safe(RefitOutcomes.eventLabel(e.type))+'</strong><small>'+
   safe([d.case,d.model,d.phase].filter(Boolean).join(" · ")||"Runtime event")+'</small></span>'+
   '<time class="mono">'+safe((e.time||"").slice(11,19))+'</time><span class="mono trace-duration">'+
   safe(formatDuration(duration))+'</span></button>';
 };
 const branch=(key,label,model,children)=>children?
  '<details class="trace-branch" data-trace-branch="'+safe(key)+'" '+(state.traceCollapsed.has(key)?"":"open")+
  '><summary><span>'+safe(label)+'</span>'+(model?'<small class="mono">'+modelIdentity(model)+'</small>':"")+'</summary><div class="trace-children">'+
  children+'</div></details>':"";
 const items=groups.map(g=>branch("phase-"+g.seq,g.label,g.model,
  g.items.map(node=>node.entries?branch("case-"+node.seq,node.name,null,node.entries.map(entry).join("")):entry(node)).join(""))).join("");
 return traceWaterfall(events)+
 '<div class="trace-toolbar"><div class="trace-filters" role="group" aria-label="Filter trace events">'+filterButtons+'</div>'+
 '<span class="trace-count">'+visible.length+' / '+events.length+' events'+(matches.length>visible.length?" · latest shown":"")+'</span></div>'+
 '<div class="trace-explorer"><div class="trace-events" aria-label="Recorded events">'+
 (items||'<p class="trace-nothing">No matching recorded events.</p>')+
 '</div><section id="traceInspector" class="trace-inspector" aria-live="polite">'+traceDetails(selected)+'</section></div>';
}

function runLog(events){if(!events.length)return "No events received yet.";
 return events.slice(-75).map(e=>{
  const d=e.details||{},time=(e.time||"").slice(11,19);
  return [time,("000"+e.seq).slice(-3),e.type.replaceAll("_"," "),d.phase,d.case,d.model,d.tools_called?.join(", "),
   d.receipt?.verified===true?"cleanup verified":d.receipt?.verified===false?"cleanup unverified":null,
   d.error||null].filter(Boolean).join("   ");
 }).join("\n");
}
async function showRun(id,refreshOnly=false){
 if(state.guest && !["demo-python-2026-11-07",C1_DEMO_ID].includes(id)){
   header("Private run");page.innerHTML=guestNote+empty("Private run","This run belongs to another visitor workspace.",'<button class="btn primary" data-action="new-agent">Import agent</button>');return;
 }
 const publicId=id===C1_DEMO_ID||id==="demo-python-2026-11-07";
 if(publicId && !(id===C1_DEMO_ID?state.c1demo:state.demo)){
   if(id===C1_DEMO_ID)state.c1demo=await req("/challenge1-demo");
   else state.demo=await req("/demo");
 }
 const publicRecord=id===C1_DEMO_ID?state.c1demo:state.demo;
 const [run,evidence]=publicId ? [publicRecord.run,publicRecord] :
   await Promise.all([req("/runs/"+id),req("/runs/"+id+"/evidence")]);
 if(location.pathname!=="/app/runs/"+id)return;
 state.runRevision++;
 const previousView=refreshOnly?snapshotRunView():null;
 const events=evidence.events||[],cases=events.filter(e=>e.type==="case_completed");
 const active=!ended(run.status);
 const diagnostic=evidence.run?.diagnostic||run.diagnostic;
 const diagnosing=diagnostic?.status==="running";
 header(active?"Run migration":"Migration review",active?3:0,"Agents / "+(run.import?.repository||"Imported agent")+" / "+(active?"Run":"Review"));
 const report=evidence.run?.report;
 const tabs=["evaluation",...(report?.proposal?["repair"]:[]),"traces","evidence"];
 const currentTab=tabs.includes(state.tab)?state.tab:"evaluation";
 const panel=currentTab==="evaluation"?renderComparison(cases,run.source,run.target,report):
  currentTab==="repair"?'<div class="stack"><h3>Supplemental instructions</h3><pre class="log">'+
   safe(report.accepted_patch?.instructions||report.proposal.instructions||"No instruction change")+
   '</pre><p class="small">'+(run.export_available?"The adaptation passed fresh original-runtime verification.":"The adaptation has no verified export.")+
   '</p></div>':
  currentTab==="traces"?traceExplorer(events):
  evidenceExplorer(run,events);
 page.innerHTML=(run.demo?guestNote:"")+'<div class="page-lead"><div><div class="row-wrap"><h1>'+safe(run.import?.repository||"Migration review")+'</h1>'+statusChip(run.status)+'</div><div class="run-model-line">'+modelIdentity(run.source)+'<span class="model-pair-sep" aria-hidden="true">→</span>'+modelIdentity(run.target)+'</div><p class="run-identifier mono">'+safe(run.id)+'</p></div><div class="button-row">'+
 (active?'<button data-action="cancel-run" data-id="'+safe(id)+'" class="btn">Cancel</button>':"")+
 (!active&&!run.demo&&run.diagnostics_available&&!diagnostic?
  '<button data-action="diagnose-run" data-id="'+safe(id)+'" class="btn">'+ico("code")+' Run diagnostic</button>':"")+
 (diagnostic?'<button data-action="inspect-diagnostic" class="btn">'+ico("eye")+' '+(diagnosing?"Diagnostic running":"Inspect diagnostic")+'</button>':"")+
 (id==="demo-python-2026-11-07"?'<a class="btn" data-nav href="/app/replay">'+ico("eye")+' Watch execution</a>':"")+
 '<button data-action="evidence-download" data-id="'+safe(id)+'" class="btn">'+ico("download")+' Download evidence</button>'+
 (run.export_available?'<button data-action="artifact-download" data-id="'+safe(id)+'" class="btn primary">'+ico("download")+' Export verified configuration</button>':"")+
 '</div></div>'+
 (run.error?'<div class="notice" style="margin-bottom:18px">'+safe("Execution result: "+String(run.error).replaceAll("_"," "))+'</div>':"")+
 (["evaluation","repair"].includes(currentTab)?decisionSurface(run,events):"")+
 '<div class="run-layout'+(["traces","evidence"].includes(currentTab)?" investigation-layout":"")+'"><div class="stack"><section class="card inner comparison-card"><div class="between"><div><h2>'+(active?"Executing migration":"Review migration results")+'</h2><p style="font-size:13px;margin-top:5px">Case outcomes, original traces and verification receipts from this run.</p></div><span class="chip bordered">'+safe(run.model_requests??run.request_attempts_logged??0)+' / '+safe(run.budget)+' requests</span></div>'+
 '<div class="tabs" style="margin-top:19px">'+tabs.map(t=>'<button class="tab '+(t===currentTab?"active":"")+'" data-action="tab" data-tab="'+t+'">'+(t==="traces"?"Trace":t.charAt(0).toUpperCase()+t.slice(1))+'</button>').join("")+'</div>'+
 '<div class="tab-panel" id="runPanel">'+panel+'</div></section>'+
 (active?'<div class="hint-note">'+ico("clock")+' This run is persisted. You can leave this page and reopen it from Runs. Inference is never automatically retried.</div>':
 run.export_available?'<div class="hint-note">'+ico("check")+' Export is available only because the original application passed the fresh verification gate. Compatibility is established for the evaluated cases, not every possible behavior.</div>':
 '<div class="hint-note">'+ico("alert")+' No verified export is available. Review the failed baseline, model calls and verification evidence.</div>')+'</div>'+
 '<aside class="stack"><section class="card inner side-facts"><h3>Run details</h3><div class="pair-line"><span class="sub">Run ID</span><span class="mono">'+safe(run.id)+'</span></div><div class="pair-line"><span class="sub">Source</span><span>'+safe(run.source)+'</span></div><div class="pair-line"><span class="sub">Target</span><span>'+safe(run.target)+'</span></div><div class="pair-line"><span class="sub">Started</span><span>'+safe(formatTime(run.started_at))+'</span></div><div class="pair-line"><span class="sub">Requests</span><span>'+safe(run.model_requests??0)+'</span></div><div class="pair-line"><span class="sub">Export</span><span>'+(run.export_available?"Verified":"Withheld")+'</span></div></section>'+
 recentRunEvents(events,active)+ '<section class="card inner side-facts"><h3>Environment</h3><div class="pair-line"><span class="sub">Runtime</span><span>'+safe(run.import?.discovery?.runtime||"Imported application")+'</span></div><div class="pair-line"><span class="sub">Isolation</span><span>gVisor</span></div><div class="pair-line"><span class="sub">Network</span><span>Restricted</span></div></section></aside></div>'+
 '<div class="flow-footer"><button class="btn" data-action="show-runs">'+ico("back")+' Back to runs</button></div>';
 restoreRunView(previousView);
 if(active)subscribe(id);
 else{
  stopStream();
  if(diagnosing)state.refreshHandle=setTimeout(()=>{
   state.refreshHandle=null;
   if(location.pathname==="/app/runs/"+id)showRun(id,true).catch(err=>notify(err.message));
  },2000);
 }
}
function subscribe(id){
 if(state.streamId===id&&state.stream)return;
 stopStream();
 state.streamId=id;
 const source=new EventSource(API+"/runs/"+id+"/events?after=0");
 state.stream=source;
 source.onmessage=event=>{
  try{
   const e=JSON.parse(event.data);
   if(e.seq<=state.streamCursor)return;
   state.streamCursor=e.seq;
   if(state.refreshHandle)clearTimeout(state.refreshHandle);
   state.refreshHandle=setTimeout(()=>{state.refreshHandle=null;if(location.pathname==="/app/runs/"+id)showRun(id,true).catch(err=>notify(err.message));},e.type==="terminal"?0:220);
  }catch(error){console.error("Invalid run event",error);}
 };
 // SSE connections expire after ten seconds. EventSource reconnects automatically.
 source.onerror=()=>{};
}
async function download(id,type){
 if(state.guest && !["demo-python-2026-11-07",C1_DEMO_ID].includes(id))throw Error("This artifact belongs to another visitor workspace.");
 const publicId=id===C1_DEMO_ID||id==="demo-python-2026-11-07";
 if(publicId && !(id===C1_DEMO_ID?state.c1demo:state.demo)){
   if(id===C1_DEMO_ID)state.c1demo=await req("/challenge1-demo");
   else state.demo=await req("/demo");
 }
 const publicRecord=id===C1_DEMO_ID?state.c1demo:state.demo;
 const data=publicId
   ?(type==="artifact"?publicRecord.artifact:publicRecord)
   :await req("/runs/"+id+"/"+type);
 if(!data)throw Error("This example has no verified artifact.");
 const body=JSON.stringify(data,null,2),file=new Blob([body],{type:"application/json"});
 const url=URL.createObjectURL(file),link=document.createElement("a");
 link.href=url;link.download=id+"-"+type+".json";document.body.appendChild(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function searchOverlay(event){
 openWorkspacePalette({
  escape:safe, refresh:refreshWorkspace, trigger:event?.currentTarget,
  items:()=>[
   ...[["Overview",""],["Agents","/agents"],["Runs","/runs"],["Evidence","/evidence"],["Settings","/settings"]]
    .map(([title,path])=>({title,sub:"Go to page",group:"Navigation",action:"navigate",id:"/app"+path})),
   {title:"Import agent",sub:"GitHub or ZIP · no account required",group:"Actions",action:"navigate",
    id:"/app/agents/new"},
   ...state.projects.map(p=>({title:p.repository||"Uploaded ZIP",sub:p.id,group:"Agents",action:"project",id:p.id})),
   ...state.runs.map(r=>({title:r.id,sub:[r.source,r.target,statusText[r.status]].filter(Boolean).join(" · "),
    group:"Runs",action:"run",id:r.id}))
  ],
  activate:item=>{
   if(item.action==="project")chooseProject(item.id).catch(e=>notify(e.message));
   else navigate(item.action==="run"?"/app/runs/"+item.id:item.id);
  }
 });
}
async function show(){
 stopStream();
 if(window.RefitReplay)RefitReplay.stop();
 page.innerHTML='<div class="small muted">Loading…</div>';
 const pathname=location.pathname;
 document.body.classList.toggle("replay-film",pathname==="/app/replay"&&new URLSearchParams(location.search).get("studio")==="1");
 if(pathname==="/app"){await overview();return;}
 if(pathname==="/app/replay"){
  header("Execution replay");
  document.body.dataset.workspacePage="replay";
  const evidence=state.demo||await req("/demo");
  page.innerHTML=RefitReplay.shell(evidence);
  RefitReplay.mount(evidence);
  return;
 }
 if(pathname==="/app/agents"){await agents();return;}
 if(pathname==="/app/agents/new"){
  const projectId=new URLSearchParams(location.search).get("project");
  if(projectId&&(!state.wizard||state.wizard.project?.id!==projectId)){
   await refreshWorkspace();const project=state.projects.find(p=>p.id===projectId);
   if(project)state.wizard={step:1,project};
  }
  await flow();return;
 }
 if(pathname==="/app/runs"){await runs();return;}
 if(pathname==="/app/evidence"){await evidenceIndex();return;}
 if(pathname==="/app/settings"){await settings();return;}
 const match=pathname.match(/^\/app\/runs\/(app-[0-9a-f]{16}|demo-python-2026-11-07|demo-diagnostic-2026-11-08)$/);
 if(match){
  const query=new URLSearchParams(location.search);
  state.tab=query.get("view")||"evaluation";
  state.traceSelected=query.get("event");
  state.evidenceSelected=query.get("observation");
  state.traceFilter="all";
  state.traceCollapsed.clear();
  await showRun(match[1]);return;
 }
 navigate("/app",true);
}
document.addEventListener("click",async event=>{
 const nav=event.target.closest("a[data-nav]");
 if(nav){event.preventDefault();navigate(nav.pathname+nav.search);return;}
 const button=event.target.closest("[data-action]");if(!button)return;
 const action=button.dataset.action,id=button.dataset.id;
 try{
  if(action==="try-live"){
   button.disabled=true;
   const previous=button.innerHTML;
   button.innerHTML=ico("clock")+" Starting live migration…";
   try{
     const started=await req("/try",{});
     if(!/^app-[0-9a-f]{16}$/.test(started.id))throw Error("Run identity was not returned.");
     state.username="Live visitor";state.trial=true;state.guest=false;
     document.body.classList.remove("guest-session");
     el("avatar").textContent="V";
     el("workspaceIdentity").textContent="Live visitor";
     document.querySelector("[data-trial-start]")?.remove();
     state.wizard=null;
     await refreshWorkspace();
     navigate("/app/runs/"+started.id);
   }catch(error){
     button.disabled=false;button.innerHTML=previous;
     throw error;
   }
  }
  else if(action==="overview-trace"){
   navigate("/app/runs/"+id+"?view=traces&event="+encodeURIComponent(button.dataset.seq));
  }
  else if(action==="new-agent"){state.wizard=null;navigate("/app/agents/new");}
  else if(action==="example-agent"){
   const demo=state.demo;
   const module=demo.artifact?.module;
   state.wizard={step:1,project:{
     id:"public-example",repository:"Published Python example",
     file_count:13,revision:demo.run.started_at,
     discovery:{runtime:"python",entry:module?"python -m "+module:"Recorded Python application",provider:"OpenAI-compatible Chat Completions",setup:"Original-runtime evaluation contract was independently verified."}},
     source:demo.run.source,target:demo.run.target,budget:demo.run.budget,setup:""};
   navigate("/app/agents/new");
  }
  else if(action==="show-runs")navigate("/app/runs");
  else if(action==="source-report"){
   const p=state.wizard.project,status=button.dataset.status,offset=Number(button.dataset.offset||0);
   const output=el("sourceReport");
   const result=await req("/projects/"+p.id+"/source?status="+encodeURIComponent(status)+"&offset="+offset);
   if(!output?.isConnected)return;
   if(!offset)output.innerHTML='<div class="file-list" style="margin-top:12px"></div>';
   else button.remove();
   output.querySelector(".file-list").insertAdjacentHTML("beforeend",result.files.length?result.files.map(file=>
    '<div><code>'+safe(file.path)+'</code> <span class="hint">'+safe(file.reason)+'</span></div>').join(""):'<div>No '+safe(status)+' files.</div>');
   const next=offset+result.files.length;
   if(next<result.total)output.insertAdjacentHTML("beforeend",'<button type="button" class="btn" data-action="source-report" data-status="'+status+'" data-offset="'+next+'">Show more</button>');
  }
  else if(action==="adjust-source"){
   const project=state.wizard.project;
   history.replaceState(history.state,"","/app/agents/new");
   state.wizard=null;
   await flow();
   const repository=String(project.repository||"");
   if(!repository||repository==="Uploaded ZIP"){
     page.querySelector('[data-import-mode="zip"]')?.click();
     el("zip").focus();
     notify("Choose a revised ZIP archive. The existing imported snapshot and its run evidence are retained.");
     return;
   }
   el("repository").value=/^https?:\/\//.test(repository)?repository:"https://github.com/"+repository;
   el("revision").value=project.revision||"";
   el("sourceDirectory").value=project.directory||"";
   el("advancedImport").open=true;
   el("sourceDirectory").focus();
  }
  else if(action==="run")navigate("/app/runs/"+id+(button.dataset.view==="evidence"?"?view=evidence":""));
  else if(action==="diagnose-run"){
   button.disabled=true;
   try{
    await req("/runs/"+id+"/diagnose",{});
    state.tab="evidence";state.evidenceSelected="diagnostic";
    await showRun(id,true);
   }catch(error){button.disabled=false;throw error;}
  }
  else if(action==="inspect-diagnostic"){
   state.tab="evidence";state.evidenceSelected="diagnostic";
   await showRun(location.pathname.split("/").pop(),true);
  }
  else if(action==="project")await chooseProject(id);
  else if(action==="remove"){
   if(!confirm("Delete this imported source snapshot from your workspace? Existing run evidence is retained."))return;
   await req("/projects/"+id+"/remove",{});await agents();
  }else if(action==="flow-back"){history.replaceState(history.state,"","/app/agents/new");state.wizard=null;await flow();}
  else if(action==="flow-config"){
   const picked=el("applicationBoundary")?.value;
   const d=state.wizard.project.discovery;
   const app=picked==="python"||picked==="typescript"?{runtime:picked,entry:null}:
     picked?d.applications[Number(picked)]:null;
   if(!app&&d.runtime==="mixed")throw Error("Choose an application boundary before continuing.");
   if(app?.entry!==state.wizard.application?.entry||app?.runtime!==state.wizard.application?.runtime)state.wizard.setup="";
   state.wizard.application=app;state.wizard.step=2;await flow();
  }
  else if(action==="flow-inspect"){
   state.wizard.source=el("source")?.value;state.wizard.target=el("target")?.value;
   if(el("setup"))state.wizard.setup=state.wizard.advanced?el("setup").value:
     JSON.stringify(readSetup(selectedDiscovery()),null,2);
   state.wizard.budget=el("budget")?.value;state.wizard.step=1;await flow();
  }else if(action==="toggle-setup"){
   const d=selectedDiscovery();
   const setup=readSetup(d);
   if(state.wizard.advanced){
    const field=d.runtime==="typescript"?"entry":"module";
    const fields=["format","mode",field,"args","cases","instruction_env","instruction_base","provider_env"];
    const caseKeys=["name","split","prompt","stdout","json_contains","tool","tool_arguments","tool_result","forbidden_tools","state"];
    if(!setup||typeof setup!=="object"||Object.keys(setup).some(key=>!fields.includes(key))||
       (setup.mode&&setup.mode!=="managed")||(setup.format&&setup.format!=="refit.agent.v1")||
       !Array.isArray(setup.args)||setup.args.some(arg=>typeof arg!=="string"||arg.includes("\n"))||
       !Array.isArray(setup.cases)||
       setup.cases.some(item=>!item||Object.keys(item).some(key=>!caseKeys.includes(key))))
      throw Error("This contract uses fields that require the JSON editor.");
   }
   state.wizard.setup=JSON.stringify(setup,null,2);
   state.wizard.advanced=!state.wizard.advanced;
   const section=page.querySelector(".setup-fields");
   section.outerHTML=setupFields(d);
   (state.wizard.advanced?el("setup"):el("entryPoint")).focus();
  }else if(action==="add-case"){
   const fields=el("caseFields");
   if(fields.childElementCount>=6)throw Error("Use at most six evaluation cases.");
   fields.insertAdjacentHTML("beforeend",caseFields({},el("extraSplit").value,true,true));
   fields.lastElementChild.querySelector('[data-case="name"]').focus();
  }else if(action==="remove-case"){
   button.closest(".setup-case").remove();
   el("extraSplit").focus();
  }else if(action==="start-migration")await startMigration();
  else if(action==="cancel-run"){await req("/runs/"+id+"/cancel",{});await showRun(id);}
  else if(action==="evidence-select"){
   const item=state.evidenceItems.find(entry=>entry.key===button.dataset.key);
   const inspector=el("evidenceInspector");
   if(!item||!inspector)return;
   state.evidenceSelected=item.key;
   const url=new URL(location.href);
   url.searchParams.set("observation",item.key);
   history.replaceState(history.state,"",url);
   inspector.innerHTML=evidenceDetail(item);
   page.querySelectorAll(".evidence-entry").forEach(entry=>{
    const selected=entry.dataset.key===item.key;
    entry.classList.toggle("selected",selected);
    entry.setAttribute("aria-pressed",String(selected));
   });
  }
  else if(action==="trace-filter"){
   state.traceFilter=button.dataset.filter;
   const panel=el("runPanel");
   if(panel)panel.innerHTML=traceExplorer(state.traceEvents);
  }
  else if(action==="trace-select"){
   const entry=state.traceEvents.find(e=>String(e.seq)===String(button.dataset.seq));
   if(!entry)return;
   state.traceSelected=entry.seq;
   const url=new URL(location.href);
   url.searchParams.set("event",entry.seq);
   history.replaceState(history.state,"",url);
   const details=el("traceInspector");
   if(details)details.innerHTML=traceDetails(entry);
   page.querySelectorAll(".trace-entry").forEach(item=>{
    const chosen=item.dataset.seq===String(entry.seq);
    item.classList.toggle("selected",chosen);
    item.setAttribute("aria-pressed",String(chosen));
   });
  }
  else if(action==="retry-page")await show();
  else if(action==="evidence-download"||action==="artifact-download")await download(id,action==="evidence-download"?"evidence":"artifact");
  else if(action==="inspect-evidence"){
   state.tab="evidence";state.evidenceSelected=button.dataset.key;
   const url=new URL(location.href);
   url.searchParams.set("view","evidence");url.searchParams.set("observation",state.evidenceSelected);
   url.searchParams.delete("event");
   history.replaceState(history.state,"",url);
   await showRun(location.pathname.split("/").pop());
   page.querySelector("#runPanel")?.scrollIntoView({block:"start"});
  }
  else if(action==="tab"){
   state.tab=button.dataset.tab;
   const url=new URL(location.href);
   url.searchParams.set("view",state.tab);
   if(state.tab!=="traces")url.searchParams.delete("event");
   if(state.tab!=="evidence")url.searchParams.delete("observation");
   history.replaceState(history.state,"",url);
   await showRun(location.pathname.split("/").pop());
  }
  else if(action==="signout"){await req("/logout",{});location.assign("/");}
 }catch(e){notify(e.message);}
});
document.addEventListener("toggle",event=>{
 const key=event.target.dataset?.traceBranch;
 if(!key||!event.target.isConnected)return;
 if(event.target.open)state.traceCollapsed.delete(key);else state.traceCollapsed.add(key);
},true);
document.addEventListener("keydown",event=>{
 const selected=event.target.closest?.(".trace-entry");
 if(!selected||!["ArrowUp","ArrowDown","Home","End"].includes(event.key))return;
 const rows=[...document.querySelectorAll(".trace-entry")].filter(row=>row.getClientRects().length);
 const current=rows.indexOf(selected);
 const next=event.key==="Home"?0:event.key==="End"?rows.length-1:
  Math.max(0,Math.min(rows.length-1,current+(event.key==="ArrowDown"?1:-1)));
 event.preventDefault();
 rows[next]?.focus();
 rows[next]?.click();
});
document.addEventListener("change",event=>{
 const field=event.target.id;
 if(field!=="runStatus"&&field!=="runPeriod")return;
 if(field==="runStatus")state.runsFilter=event.target.value;
 else state.runsPeriod=event.target.value;
 const rows=el("runRecords");
 if(rows)rows.innerHTML=runIndexRows();
});
document.addEventListener("input",event=>{
 if(event.target.id==="agentQuery"){
  const query=event.target.value.trim().toLowerCase();
  const rows=[...page.querySelectorAll("[data-agent-row]")];
  rows.forEach(row=>{row.hidden=!row.textContent.toLowerCase().includes(query)});
  el("agentNoMatches").hidden=rows.some(row=>!row.hidden);
  return;
 }
 if(event.target.id!=="runQuery")return;
 state.runsQuery=event.target.value;
 const rows=el("runRecords");
 if(rows)rows.innerHTML=runIndexRows();
});
document.addEventListener("click",event=>{
 const tab=event.target.closest("[data-import-mode]");
 if(!tab)return;
 const mode=tab.dataset.importMode;
 if(!el("method"))return;
 el("method").value=mode;
 const zip=mode==="zip";
 el("zipField").hidden=!zip;el("githubFields").hidden=zip;
 el("repository").required=!zip;el("zip").required=zip;
 el("advancedImport").hidden=zip;
 for(const item of document.querySelectorAll("[data-import-mode]")){
   const selected=item.dataset.importMode===mode;
   item.classList.toggle("active",selected);
   item.setAttribute("aria-pressed",String(selected));
 }
});
document.addEventListener("submit",async event=>{
 if(event.target.id==="importForm"){event.preventDefault();await importProject();}
});
el("search").addEventListener("click",searchOverlay);
if(/Mac|iPhone|iPad/.test(navigator.platform))el("commandKey").textContent="⌘ K";
document.addEventListener("click",event=>{
 const navigation=document.querySelector("#mobileNavigation[open]");
 if(navigation&&(!navigation.contains(event.target)||event.target.closest(".mobile-nav a")))navigation.open=false;
 const menu=document.querySelector(".workspace-account[open]");
 if(menu&&(!menu.contains(event.target)||event.target.closest("[data-nav]")))menu.open=false;
});
document.addEventListener("keydown",event=>{
 if(event.key!=="Escape")return;
 for(const menu of document.querySelectorAll(".workspace-account[open],#mobileNavigation[open]")){
   menu.open=false;menu.querySelector("summary")?.focus();
 }
});
document.addEventListener("keydown",event=>{
 if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();searchOverlay();}
});
window.addEventListener("popstate",()=>show().catch(pageFailure));
(async()=>{
 try{
  const reviewCode=new URLSearchParams(location.hash.slice(1)).get("review");
  if(reviewCode!==null){
    history.replaceState(null,"",location.pathname+location.search);
    try{await req("/review-session",{code:reviewCode});}catch(error){notify(error.message);}
  }
  const session=await req("/session");
  if(session.mode!=="account"){throw Error("Account session endpoint unavailable.");}
  state.username=session.username||null;
  state.trial=session.trial===true;
  state.guest=!state.username;
  if(state.guest){
    el("avatar").textContent="G";document.body.classList.add("guest-session");
    const button=document.createElement("button");button.type="button";
    button.dataset.action="new-agent";button.dataset.trialStart="1";
    button.className="btn compact";button.textContent="Import agent";
    el("avatar").closest("details").before(button);
    await refreshWorkspace();
  }else {
   el("avatar").textContent=state.username.charAt(0).toUpperCase();
   el("workspaceIdentity").textContent=state.username;
  }
  await show();
 }catch(e){pageFailure(e);}
})();