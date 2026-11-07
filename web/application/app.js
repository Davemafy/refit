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
const state={username:null,guest:false,demo:null,projects:[],runs:[],capabilities:null,wizard:null,tab:"evaluation",stream:null,streamId:null,streamCursor:0,refreshHandle:null,search:null,runRevision:0};
const statusText={
 compatible_on_sample:"Compatible on evaluated cases",
 verified_adaptation:"Verified repair",
 source_baseline_insufficient:"Source baseline failed",
 export_failed_original_runner_verification:"Export verification failed",
 interrupted:"Interrupted",failed:"Execution failed",
 inference_budget_exhausted:"Budget exhausted",cancelled:"Cancelled",
 running:"Running",cancelling:"Cancelling"
};
const ended=status=>!["running","cancelling"].includes(status);
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
 if(response.status===401){
   if(!state.guest)location.assign("/login?next="+encodeURIComponent(location.pathname));
   throw Error("Sign in to access your private workspace or run a migration.");
 }
 if(!response.ok)throw Error(payload.error?.message||"Request failed ("+response.status+").");
 return payload;
}
const formatTime=value=>{if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString();};
const formatDuration=value=>typeof value==="number"?value.toFixed(1)+" s":"—";
function header(label,step=0,crumb){
 const node=el("crumb");node.textContent=crumb||label;
 const steps=el("steps");
 steps.hidden=!step;
 if(step){
  const labels=["Inspect","Configure","Run","Review"];
  steps.innerHTML=labels.map((name,i)=>
   '<span class="step '+(step===i+1?"active":step>i+1?"done":"")+'"><span class="num">'+(step>i+1?ico("check"):i+1)+'</span>'+name+'</span>'+
   (i===3?"":'<span class="step-sep">—</span>')).join("");
 }
 for(const link of document.querySelectorAll("a[data-nav]")){
   const href=link.getAttribute("href");
   link.classList.toggle("selected",href==="/app/agents"?location.pathname.startsWith("/app/agents"):href==="/app/runs"?location.pathname.startsWith("/app/runs"):href===location.pathname);
 }
 document.title=label+" · Refit";
}
function stopStream(){
 if(state.stream){state.stream.close();state.stream=null;}
 state.streamId=null;state.streamCursor=0;
 if(state.refreshHandle){clearTimeout(state.refreshHandle);state.refreshHandle=null;}
}
function navigate(to,replace=false){
 if(!/^\/app(?:\/|$)/.test(to))return;
 if(replace)history.replaceState({},"",to);else history.pushState({},"",to);
 show().catch(e=>notify(e.message));
}
async function refreshWorkspace(){
 if(state.guest){
   if(!state.demo)state.demo=await req("/demo");
   state.projects=[];
   state.runs=[state.demo.run];
   return;
 }
 const [projects,runs]=await Promise.all([req("/projects"),req("/runs")]);
 state.projects=projects.projects||[];
 state.runs=runs.runs||[];
}
const lead=(title,subtitle,right="")=>'<div class="page-lead"><div><h1>'+safe(title)+'</h1><p>'+safe(subtitle)+'</p></div>'+right+'</div>';
const empty=(title,desc,button)=>'<div class="empty"><div class="empty-icon">'+ico("layers")+'</div><h2>'+safe(title)+'</h2><p>'+safe(desc)+'</p>'+button+'</div>';
const importButton='<button class="btn primary" data-action="new-agent">'+ico("plus")+' Import agent</button>';
const guestNote='<div class="hint-note" style="margin-bottom:22px">'+ico("eye")+' Public, read-only preview. This example comes from a verified November 7 Vultr migration; no inference runs while you browse. <a href="/login?next=/app/agents/new" style="text-decoration:underline;color:#fff">Sign in to import your own agent</a>.</div>';
async function overview(){
 header("Overview");
 await refreshWorkspace();
 page.innerHTML=(state.guest?guestNote:"")+lead(state.guest?"Explore Refit":"Your workspace",state.guest?"Inspect a recorded migration without signing in.":"Manage application agents and review real migration evidence.",importButton)+
 '<div class="metrics" style="margin-bottom:25px"><div class="metric"><strong>'+state.projects.length+'</strong><span>Imported agents</span></div><div class="metric"><strong>'+state.runs.length+'</strong><span>Recent runs</span></div><div class="metric"><strong>'+state.runs.filter(r=>r.status==="compatible_on_sample"||r.status==="verified_adaptation").length+'</strong><span>Verified results</span></div><div class="metric"><strong>'+state.runs.filter(r=>!ended(r.status)).length+'</strong><span>Active migrations</span></div></div>'+
 '<section class="card inner"><div class="between"><h3>Recent migrations</h3><a href="/app/runs" data-nav class="btn compact">View all '+ico("arrow")+'</a></div><div style="margin-top:16px">'+runTable(state.runs.slice(0,5))+'</div></section>'+
 '<section class="card inner" style="margin-top:18px"><h3>'+(state.guest?"Try the migration workflow":"Get started")+'</h3><p style="margin:8px 0 18px">'+(state.guest?"Explore the import and verification steps with a published example. Running your own code requires an account.":"Import a pinned repository or ZIP, confirm its original entry point and evaluation cases, then choose a replacement model.")+'</p>'+(state.guest?'<div class="button-row"><button data-action="example-agent" class="btn primary">Inspect the example '+ico("arrow")+'</button><a href="/login?next=/app/agents/new" class="btn">Sign in to import</a></div>':importButton)+'</section>';
}
const runTable=runs=>runs.length?
 '<div style="overflow-x:auto"><table class="table"><thead><tr><th>Run</th><th>Models</th><th>Status</th><th>Started</th></tr></thead><tbody>'+
 runs.map(r=>'<tr><td><button class="link-btn mono" data-action="run" data-id="'+safe(r.id)+'">'+safe(r.id)+'</button></td><td>'+safe(r.source||"—")+' → '+safe(r.target||"—")+'</td><td>'+statusChip(r.status)+'</td><td>'+safe(formatTime(r.started_at))+'</td></tr>').join("")+'</tbody></table></div>':
 empty("No runs yet","Your migrations will appear here. Import an agent to start.",importButton);
async function agents(){
 header("Agents");
 await refreshWorkspace();
 page.innerHTML=(state.guest?guestNote:"")+lead("Agents",state.guest?"Inspect the recorded sample or sign in to import your own agent.":"Your imported application source snapshots and detected runtimes.",importButton)+
 (state.guest?'<section class="card inner" style="margin-bottom:20px"><h3>Recorded Python application</h3><p style="margin:10px 0 16px">An independent knowledge-base application ran in Vultr gVisor. The source and replacement models passed the recorded cases and fresh export check.</p><div class="button-row"><button class="btn primary" data-action="example-agent">Inspect example '+ico("arrow")+'</button><button class="btn" data-action="run" data-id="demo-python-2026-11-07">View verified migration</button></div></section>':"")+
 (state.projects.length?
 '<div class="card" style="overflow-x:auto"><table class="table"><thead><tr><th>Source</th><th>Runtime</th><th>Entry point</th><th>Files</th><th></th></tr></thead><tbody>'+
 state.projects.map(p=>'<tr><td><button class="link-btn" data-action="project" data-id="'+safe(p.id)+'">'+safe(p.repository||"Uploaded ZIP")+'</button><div class="small muted mono">'+safe(p.id)+'</div></td><td>'+safe(p.discovery?.runtime||"Unknown")+'</td><td>'+safe(p.discovery?.entry||"Configuration required")+'</td><td>'+safe(p.file_count||0)+'</td><td><button data-action="remove" data-id="'+safe(p.id)+'" class="btn compact danger">Remove</button></td></tr>').join("")+'</tbody></table></div>':
 empty("No agents imported","Import a pinned GitHub revision or a ZIP. Refit will inspect the source before any paid execution.",importButton));
}
async function runs(){
 header("Runs");
 await refreshWorkspace();
 page.innerHTML=(state.guest?guestNote:"")+lead("Runs",state.guest?"Published example run; private user runs are never listed here.":"Migration history with actual inference, evaluation and sandbox evidence.",importButton)+'<section class="card">'+runTable(state.runs)+'</section>';
}
async function evidenceIndex(){
 header("Evidence");
 await refreshWorkspace();
 page.innerHTML=(state.guest?guestNote:"")+lead("Evidence","Open a migration to inspect its case results, model requests, tool events and sandbox cleanup.")+
 (state.runs.length?'<div class="card">'+runTable(state.runs)+'</div>':empty("No evidence yet","Evidence is generated by actual migrations. Nothing is simulated here.",importButton));
}
async function settings(){
 header("Settings");
 if(state.guest){
   page.innerHTML=guestNote+lead("Settings","Guest browsing does not create an account or consume inference credits.")+
   '<section class="card inner" style="max-width:780px"><h3>Guest access</h3><p style="margin:10px 0 22px">You can inspect published migration evidence without signing in. Source uploads, project history, paid migration execution, and private artifact downloads remain account-scoped.</p><a class="btn primary" href="/login?next=/app/settings">Sign in '+ico("arrow")+'</a></section>';
   return;
 }
 const config=await req("");
 page.innerHTML=lead("Settings","Your developer account and execution limits.")+
 '<div class="card inner" style="max-width:800px"><h3>Account</h3><div class="fact"><span>'+ico("lock")+'</span><span class="sub">Signed in as</span><strong>'+safe(state.username)+'</strong></div><div class="fact"><span>'+ico("shield")+'</span><span class="sub">Isolation</span><strong>Owner-scoped projects and runs</strong></div><div class="fact"><span>'+ico("clock")+'</span><span class="sub">Per-run limit</span><strong>'+safe(config.max_requests)+' requests</strong></div><div class="fact"><span>'+ico("clock")+'</span><span class="sub">Daily allowance</span><strong>'+safe(config.account_reserved_today)+' / '+safe(config.account_daily_allowance)+' reserved</strong></div><div class="fact"><span>'+ico("box")+'</span><span class="sub">Worker</span><strong>Isolated gVisor execution</strong></div><p class="small" style="margin:18px 0">Releases, limits and supported runtimes are documented publicly. Live execution requires explicit authorization and is subject to a shared global ceiling.</p><button class="btn" data-action="signout">Sign out</button></div>';
}
function wizardIntro(){
 return '<div class="import-header"><div><h1>Bring your agent</h1><p>Start with the code you already have. We’ll inspect the agent before changing anything.</p></div></div>';
}
const importPathSteps='<div class="import-next"><div><span>'+ico("code")+'</span><strong>Inspect</strong><p>Identify the original runtime and model boundary.</p></div><div><span>'+ico("layers")+'</span><strong>Configure</strong><p>Choose models and independent evaluation cases.</p></div><div><span>'+ico("shield")+'</span><strong>Verify</strong><p>Compare real execution before exporting.</p></div></div>';
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
 '<div class="hint-note">The agent must use OPENAI_BASE_URL and OPENAI_MODEL with non-streaming Chat Completions.</div>'+
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
 if(step===0 && state.guest){
   page.innerHTML='<div class="import-shell">'+wizardIntro()+
   '<section class="import-panel"><div class="import-panel-header"><div><h2>See a real migration</h2><p>Explore the evidence before bringing your own agent.</p></div><span class="import-privacy">'+ico("eye")+' Public example</span></div>'+
   '<div class="import-example"><div class="import-example-mark">'+ico("code")+'</div><div><strong>Python knowledge-base agent</strong><p>DeepSeek → GLM · 3 independently verified cases</p></div><span class="chip good">Verified</span></div>'+
   '<div class="import-actions"><p>Recorded execution from November 7. No inference is used to browse.</p><button class="btn primary" data-action="example-agent">Inspect this agent '+ico("arrow")+'</button></div></section>'+
   '<div class="import-signin">Want to bring your own agent? <a href="/signup">Create an account</a> or <a href="/login?next=/app/agents/new">sign in</a>.</div>'+
   importPathSteps+'</div>';
   return;
 }
 if(step===0){
  page.innerHTML='<div class="import-shell">'+wizardIntro()+
   '<section class="import-panel"><div class="import-panel-header"><div><h2>Where is your agent?</h2><p>Point Refit to the existing source. No code changes yet.</p></div><span class="import-privacy">'+ico("lock")+' Your workspace</span></div>'+
   '<div class="import-tabs" role="group" aria-label="Source type"><button type="button" class="import-tab active" data-import-mode="github" aria-pressed="true">'+ico("git")+' GitHub repository</button><button type="button" class="import-tab" data-import-mode="zip" aria-pressed="false">'+ico("upload")+' Upload ZIP</button></div>'+
   '<form id="importForm"><input type="hidden" id="method" value="github">'+
   '<div class="import-form-body"><div id="githubFields"><label class="field" for="repository">Repository URL</label><div class="import-input-wrap"><span class="import-input-icon">'+ico("git")+'</span><input class="import-primary-input" id="repository" type="url" placeholder="https://github.com/owner/repository" autocomplete="url" spellcheck="false" required></div><p class="import-helper">Refit pins the commit and downloads selected source files. Build output, caches and binary assets are skipped by default.</p></div>'+
   '<div id="zipField" hidden><label class="field" for="zip">Source archive</label><input id="zip" class="control import-file" type="file" accept=".zip,application/zip"><p class="import-helper">Up to 32 MiB compressed. Refit reads eligible files within the 12 MiB source budget.</p></div>'+
   '<details class="import-advanced" id="advancedImport"><summary>Advanced options '+ico("arrow")+'</summary><div class="import-advanced-fields"><label class="field" for="revision">Exact commit SHA <span class="hint">Optional · overrides latest commit</span></label><input class="control mono" id="revision" placeholder="40-character commit hash" maxlength="40" autocomplete="off" spellcheck="false"><label class="field" for="repoToken">Private repository token <span class="hint">Optional · used only for this import</span></label><input type="password" id="repoToken" class="control mono" placeholder="GitHub read token" autocomplete="new-password" spellcheck="false" data-lpignore="true"><label class="field" for="sourceDirectory">Application directory <span class="hint">Optional · relative to repository root</span></label><input class="control mono" id="sourceDirectory" placeholder="apps/support-agent" spellcheck="false"><label class="field" for="sourceFiles">Source file override <span class="hint">Optional · one path per line relative to the application directory</span></label><textarea class="control mono" id="sourceFiles" rows="3" spellcheck="false"></textarea></div></details></div>'+
   '<div class="import-actions"><p>'+ico("shield")+' Private inspection. No model calls or sandbox execution at this step.</p><button class="btn primary" type="submit">Inspect agent '+ico("arrow")+'</button></div></form></section>'+importPathSteps+'</div>';
  return;
 }
 const p=state.wizard.project,d=selectedDiscovery();
 if(step===1){
   const features=[["Agent entry point",d.entry||"Not confidently detected"],["Runtime",d.runtime||"Unknown"],["Provider",d.provider||"Not detected"],["Dependencies",d.dependencies?.length ? d.dependencies.join(", ") : "Not reported"],["Tools",d.tool||"Not independently enumerated"],["Provider signals",d.provider_signals?.join(", ")||"Not detected"]];
   const files=d.evaluation_files||[];
   page.innerHTML=lead("Inspect your agent","Review the detected runtime and confirm the original entry point.")+
   '<section class="card"><div class="repo-card-head"><div class="repo-mark">'+ico("git")+'</div><div style="flex:1"><h3>'+safe(p.repository||"Uploaded ZIP")+'</h3><p class="small mono">'+safe(p.revision||p.id)+'</p></div><span class="chip bordered">'+safe(p.file_count)+' files inspected</span></div>'+
   '<div class="split-panel"><div>'+features.map(f=>'<div class="fact"><span class="muted">'+ico(f[0]==="Runtime"?"code":f[0]==="Tools"?"layers":"box")+'</span><strong>'+safe(f[0])+'</strong><span class="value">'+safe(f[1])+'</span></div>').join("")+'</div>'+
   '<div><h3 style="margin-bottom:12px">Possible test files</h3><p class="small">These are static hints. Confirm the entry point and choose independent checks before authorizing a run.</p><div class="file-list" style="margin-top:14px">'+(files.length?files.map(f=>'<div>'+ico("file")+' '+safe(f)+'</div>').join(""):'<div>No individual test-file paths reported.</div>')+'</div></div></div></section>'+
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
   (d.runnable===false?'<div class="notice" style="margin-top:18px">'+safe(d.setup||"Unsupported runtime")+'</div>':d.setup?'<p style="margin-top:16px;font-size:13px">'+safe(d.setup)+'</p>':'')+
   '<div class="flow-footer"><button class="btn" data-action="flow-back">'+ico("back")+' Back</button><button class="btn primary" data-action="flow-config" '+(d.runnable===false?"disabled":"")+'>Continue to configuration '+ico("arrow")+'</button></div>';
   return;
 }
 if(!state.capabilities){
   state.capabilities=state.guest
     ?{models:[state.demo.run.source,state.demo.run.target],max_requests:state.demo.run.budget}
     :await req("");
 }
 const models=state.capabilities.models||[];
 const source=state.wizard.source||models[0]||"",target=state.wizard.target||models[1]||"";
 page.innerHTML=lead("Configure migration","Choose the source and replacement models, then supply independent evaluation cases.")+
 '<div class="flow-grid"><section class="card inner stack"><label class="field">Original model <span class="hint">The model used for baseline execution.</span><select class="control" id="source">'+models.map(m=>'<option '+(source===m?"selected":"")+' value="'+safe(m)+'">'+safe(m)+'</option>').join("")+'</select></label>'+
 '<label class="field">Replacement model <span class="hint">The model whose behavior will be verified.</span><select class="control" id="target">'+models.map(m=>'<option '+(target===m?"selected":"")+' value="'+safe(m)+'">'+safe(m)+'</option>').join("")+'</select></label>'+
 (d.preset?'<div class="hint-note">'+safe(d.evaluation||"Reviewed native evaluation preset will be used.")+'</div>':
  setupFields(d))+
 '<label class="field">Maximum Vultr requests<input type="number" id="budget" class="control" min="1" max="'+safe(state.capabilities.max_requests)+'" value="'+safe(state.wizard.budget||state.capabilities.max_requests)+'"></label>'+
 '<label class="hstack" style="font-size:13px"><input id="authorize" type="checkbox" style="width:17px;height:17px"> I authorize this bounded live inference run.</label></section>'+
 '<aside class="card inner side-facts"><h3>Migration summary</h3><hr><div class="pair-line"><span class="sub">Source</span><span>'+safe(p.repository||"Uploaded ZIP")+'</span></div><div class="pair-line"><span class="sub">Entry point</span><span>'+safe(d.entry||"Operator-configured")+'</span></div><div class="pair-line"><span class="sub">Runtime</span><span>'+safe(d.runtime)+'</span></div><div class="pair-line"><span class="sub">Verification</span><span>Original-runtime fresh check</span></div><div class="hint-note">'+ico("shield")+' Untrusted source runs inside a bounded disposable gVisor container. No production services are enabled by default.</div></aside></div>'+
 '<div class="flow-footer"><button class="btn" data-action="flow-inspect">'+ico("back")+' Back to inspection</button>'+(state.guest?'<button class="btn primary" data-action="run" data-id="demo-python-2026-11-07">View recorded results '+ico("arrow")+'</button><a class="btn" href="/login?next=/app/agents/new">Sign in to run your agent</a>':'<button id="start" class="btn primary" data-action="start-migration">Run migration '+ico("arrow")+'</button>')+'</div>';
}
async function importProject(){
 if(state.guest){notify("Sign in before submitting a private source import.");return;}
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
 if(state.guest){notify("Sign in to authorize a live migration.");return;}
 const btn=el("start");if(btn)btn.disabled=true;
 try{
   const p=state.wizard.project,d=selectedDiscovery();
   const source=el("source").value,target=el("target").value;
   if(source===target)throw Error("Select two different models.");
   if(!el("authorize").checked)throw Error("Authorize the inference budget before starting.");
   const budget=Number(el("budget").value);
   if(!Number.isInteger(budget)||budget<1||budget>state.capabilities.max_requests)throw Error("Choose a valid request budget.");
   const body={import_id:p.id,source,target,budget,authorize:true};
   if(!d.preset)body.setup=readSetup(d);
   state.wizard.source=source;state.wizard.target=target;state.wizard.budget=budget;
   if(body.setup)state.wizard.setup=JSON.stringify(body.setup,null,2);
   const run=await req("/runs",body);
   navigate("/app/runs/"+run.id);
 }catch(e){notify(e.message);}finally{if(btn?.isConnected)btn.disabled=false;}
}
function renderComparison(cases,source,target,report){
 const base=cases.filter(e=>e.details?.phase!=="fresh_export");
 const repair=!!report?.proposal;
 const names=[...new Set(base.map(e=>e.details?.case).filter(Boolean))];
 if(!names.length)return '<div class="hint-note">No source/replacement case comparisons have been recorded yet.</div>';
 const checkLabels={stdout_matches:"Exact output",json_matches:"Structured output",
   required_tool_called:"Required tool called",required_tool_observed:"Required tool result",
   forbidden_tools_absent:"Forbidden tools absent",tool_arguments_match:"Required tool arguments",state_checks_passed:"Application state"};
 const cell=d=>{
  if(!d)return '<span class="muted">Pending</span>';
  const checks=Object.entries(checkLabels).filter(([key])=>typeof d.verdict?.[key]==="boolean");
  const tools=(d.trace||[]).flatMap(call=>call.tools_called||[]);
  return (d.passed?'<span class="chip good">'+ico("check")+' Passed</span>':
    '<span class="chip bad">'+ico("alert")+' Failed</span>')+
    '<details class="case-options comparison-checks"><summary>Case evidence</summary><ul>'+
    checks.map(([key,label])=>'<li class="'+(d.verdict[key]?"sub":"error")+'">'+
      safe(label)+(d.verdict[key]?" passed":" failed")+'</li>').join("")+
    (d.state_checks||[]).map(check=>'<li class="'+(check.passed?"sub":"error")+'">'+
      safe(check.path+" · "+check.op.replaceAll("_"," ")+" · "+check.before.status+" → "+check.after.status+(check.passed?" · passed":" · failed"))+'</li>').join("")+
    (tools.length?'<li class="sub">Model requested '+safe(tools.join(", "))+'</li>':"")+
    (Number.isInteger(d.model_requests)?'<li class="sub">'+safe(d.model_requests)+' model requests</li>':"")+
    (d.error?'<li class="error">'+safe(d.error.replaceAll("_"," "))+'</li>':"")+'</ul></details>';
 };
 return '<div style="overflow-x:auto"><table class="table"><thead><tr><th>Test case</th><th>Original · '+safe(source)+'</th><th>Replacement · '+safe(target)+'</th>'+(repair?'<th>Adapted replacement</th>':'')+'<th>Comparison</th></tr></thead><tbody>'+
 names.map(name=>{
  const original=base.find(e=>e.details.case===name&&e.details.model===source)?.details;
  const targetRuns=base.filter(e=>e.details.case===name&&e.details.model===target);
  const replacement=targetRuns.find(e=>!e.details.adapted)?.details;
  const adapted=targetRuns.filter(e=>e.details.adapted).at(-1)?.details;
  const identical=!!original?.stdout_sha256&&original.stdout_sha256===replacement?.stdout_sha256;
  const bothPassed=original?.passed&&replacement?.passed;
  return '<tr><td><strong>'+safe(name)+'</strong></td><td>'+cell(original)+'</td><td>'+cell(replacement)+'</td>'+(repair?'<td>'+cell(adapted)+'</td>':'')+'<td>'+
   (bothPassed&&identical?'<span class="chip good">Matching stdout</span>':
    bothPassed?'<span class="chip good">Both meet the checks</span>':
    original?.passed&&replacement&&!replacement.passed?'<span class="chip bad">Behavior regressed</span>':
    original&&replacement?'<span class="chip warn">Checks failed</span>':'<span class="muted">Incomplete</span>')+
   '</td></tr>';
 }).join("")+'</tbody></table></div>';
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
 if(state.guest && id!=="demo-python-2026-11-07"){
   header("Private run");page.innerHTML=guestNote+empty("Private run","Sign in to view your saved migrations.",'<a class="btn primary" href="/login?next='+encodeURIComponent(location.pathname)+'">Sign in</a>');return;
 }
 const [run,evidence]=state.guest ? [state.demo.run,state.demo] :
   await Promise.all([req("/runs/"+id),req("/runs/"+id+"/evidence")]);
 if(location.pathname!=="/app/runs/"+id)return;
 state.runRevision++;
 const events=evidence.events||[],cases=events.filter(e=>e.type==="case_completed");
 const baseCases=cases.filter(e=>e.details?.phase!=="fresh_export");
 const names=[...new Set(baseCases.map(e=>e.details?.case).filter(Boolean))];
 const matched=names.filter(name=>{
  const original=baseCases.find(e=>e.details.case===name&&e.details.model===run.source)?.details;
  const replacement=baseCases.find(e=>e.details.case===name&&e.details.model===run.target&&!e.details.adapted)?.details;
  return original?.passed&&replacement?.passed;
 }).length;
 const cleanups=events.filter(e=>e.type==="sandbox_cleanup");
 const cleaned=cleanups.filter(e=>e.details?.receipt?.verified).length;
 const active=!ended(run.status);
 header(active?"Run migration":"Migration review",active?3:4,"Agents / "+(run.import?.repository||"Imported agent")+" / "+(active?"Run":"Review"));
 const report=evidence.run?.report;
 const tabs=["evaluation",...(report?.proposal?["repair"]:[]),"traces","evidence"];
 const currentTab=tabs.includes(state.tab)?state.tab:"evaluation";
 const panel=currentTab==="evaluation"?renderComparison(cases,run.source,run.target,report):
  currentTab==="repair"?'<div class="stack"><h3>Supplemental instructions</h3><pre class="log">'+
   safe(report.accepted_patch?.instructions||report.proposal.instructions||"No instruction change")+
   '</pre><p class="small">'+(run.export_available?"The adaptation passed fresh original-runtime verification.":"The adaptation has no verified export.")+
   '</p></div>':
  currentTab==="traces"?'<pre class="log">'+safe(runLog(events))+'</pre>':
  '<div class="stack"><div class="hint-note">'+cleaned+' of '+cleanups.length+' recorded containers verified cleaned up.</div><pre class="log">'+safe(JSON.stringify({run_id:run.id,configuration_sha256:run.configuration_sha256,status:run.status,verification:run.verification||[],events:events.filter(e=>e.type==="sandbox_cleanup"||e.type==="terminal")},null,2))+'</pre></div>';
 page.innerHTML=(run.demo?guestNote:"")+'<div class="page-lead"><div><div class="row-wrap"><h1>'+safe(run.import?.repository||"Migration "+run.id)+'</h1>'+statusChip(run.status)+'</div><p>'+safe(run.source)+' → '+safe(run.target)+' · '+safe(run.id)+'</p></div><div class="button-row">'+
 (active?'<button data-action="cancel-run" data-id="'+safe(id)+'" class="btn">Cancel</button>':"")+
 '<button data-action="evidence-download" data-id="'+safe(id)+'" class="btn">'+ico("download")+' Download evidence</button>'+
 (run.export_available?'<button data-action="artifact-download" data-id="'+safe(id)+'" class="btn primary">'+ico("download")+' Export verified configuration</button>':"")+
 '</div></div>'+
 (run.error?'<div class="notice" style="margin-bottom:18px">'+safe("Execution result: "+run.error.replaceAll("_"," "))+'</div>':"")+
 '<div class="run-layout"><div class="stack"><section class="card inner"><div class="between"><div><h2>'+(active?"Executing migration":"Review migration results")+'</h2><p style="font-size:13px;margin-top:5px">'+(active?"Live execution with recorded inference, case outcomes and cleanup.":"Only observed cases and verified artifacts are shown.")+'</p></div><span class="chip bordered">'+safe(run.model_requests??run.request_attempts_logged??0)+' / '+safe(run.budget)+' requests</span></div>'+
 '<div class="metrics" style="margin-top:20px"><div class="metric"><strong>'+matched+' / '+names.length+'</strong><span>Both models passed</span></div><div class="metric"><strong>'+cleaned+' / '+cleanups.length+'</strong><span>Sandbox cleanup receipts</span></div><div class="metric"><strong>'+safe(formatDuration(run.execution_seconds))+'</strong><span>Execution duration</span></div><div class="metric"><strong>'+((run.verification||[]).filter(v=>v.passed).length)+' / '+((run.verification||[]).length)+'</strong><span>Fresh export checks</span></div></div>'+
 '<div class="tabs" style="margin-top:19px">'+tabs.map(t=>'<button class="tab '+(t===currentTab?"active":"")+'" data-action="tab" data-tab="'+t+'">'+(t==="traces"?"Trace":t.charAt(0).toUpperCase()+t.slice(1))+'</button>').join("")+'</div>'+
 '<div class="tab-panel" id="runPanel">'+panel+'</div></section>'+
 (active?'<div class="hint-note">'+ico("clock")+' This run is persisted. You can leave this page and reopen it from Runs. Inference is never automatically retried.</div>':
 run.export_available?'<div class="hint-note">'+ico("check")+' Export is available only because the original application passed the fresh verification gate. Compatibility is established for the evaluated cases, not every possible behavior.</div>':
 '<div class="hint-note">'+ico("alert")+' No verified export is available. Review the failed baseline, model calls and verification evidence.</div>')+'</div>'+
 '<aside class="stack"><section class="card inner side-facts"><h3>Run details</h3><div class="pair-line"><span class="sub">Run ID</span><span class="mono">'+safe(run.id)+'</span></div><div class="pair-line"><span class="sub">Source</span><span>'+safe(run.source)+'</span></div><div class="pair-line"><span class="sub">Target</span><span>'+safe(run.target)+'</span></div><div class="pair-line"><span class="sub">Started</span><span>'+safe(formatTime(run.started_at))+'</span></div><div class="pair-line"><span class="sub">Requests</span><span>'+safe(run.model_requests??0)+'</span></div><div class="pair-line"><span class="sub">Export</span><span>'+(run.export_available?"Verified":"Withheld")+'</span></div></section>'+
 '<section class="card inner"><h3 style="margin-bottom:17px">Execution timeline</h3><div class="timeline">'+
 [["runtime_ready","Sandbox image prepared"],["sandbox_started","Application sandbox started"],["inference_completed","Vultr inference completed"],["case_completed","Evaluation case completed"],["sandbox_cleanup","Sandbox cleaned up"]].map(([key,label])=>{
  const done=events.some(e=>e.type===key);
  return '<div class="timeline-item '+(done?"done":"")+'"><span class="small-dot"></span>'+label+'</div>';
 }).join("")+'</div></section>'+
 '<section class="card inner side-facts"><h3>Environment</h3><div class="pair-line"><span class="sub">Runtime</span><span>'+safe(run.import?.discovery?.runtime||"Imported application")+'</span></div><div class="pair-line"><span class="sub">Isolation</span><span>gVisor</span></div><div class="pair-line"><span class="sub">Network</span><span>Restricted</span></div></section></aside></div>'+
 '<div class="flow-footer"><button class="btn" data-action="show-runs">'+ico("back")+' Back to runs</button></div>';
 if(active)subscribe(id);else stopStream();
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
 if(state.guest && id!=="demo-python-2026-11-07")throw Error("Sign in to access private artifacts.");
 const data=state.guest
   ?(type==="artifact"?state.demo.artifact:state.demo)
   :await req("/runs/"+id+"/"+type);
 if(!data)throw Error("This example has no verified artifact.");
 const body=JSON.stringify(data,null,2),file=new Blob([body],{type:"application/json"});
 const url=URL.createObjectURL(file),link=document.createElement("a");
 link.href=url;link.download=id+"-"+type+".json";document.body.appendChild(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function searchOverlay(){
 const overlay=document.createElement("div");
 overlay.id="searchOverlay";overlay.setAttribute("role","dialog");overlay.setAttribute("aria-modal","true");
 overlay.style.cssText="position:fixed;inset:0;background:#000b;z-index:90;display:flex;align-items:flex-start;justify-content:center;padding:13vh 14px";
 overlay.innerHTML='<div class="card inner" style="width:100%;max-width:600px;background:#1a1b1f;max-height:70vh;overflow:auto"><div class="hstack">'+ico("search")+'<input id="searchInput" class="control" autofocus placeholder="Search your agents and runs…" aria-label="Search your agents and runs"><button class="btn compact" id="searchClose" aria-label="Close search">'+ico("close")+'</button></div><div id="searchResults" style="margin-top:15px"></div></div>';
 document.body.appendChild(overlay);
 const input=overlay.querySelector("#searchInput"),results=overlay.querySelector("#searchResults");
 function update(){
   const term=input.value.trim().toLowerCase();
   const candidates=[
    ...state.projects.map(p=>({title:p.repository||"Uploaded ZIP",sub:p.id,url:"/app/agents/new?project="+p.id,action:"project",id:p.id})),
    ...state.runs.map(r=>({title:r.id,sub:statusText[r.status]||r.status,url:"/app/runs/"+r.id,action:"run",id:r.id}))
   ].filter(x=>(x.title+" "+x.sub).toLowerCase().includes(term)).slice(0,15);
   results.innerHTML=candidates.length?candidates.map(x=>'<button class="btn" style="width:100%;justify-content:flex-start;margin-bottom:8px" data-search-action="'+x.action+'" data-search-id="'+safe(x.id)+'"><span>'+safe(x.title)+'</span><span class="muted small" style="margin-left:auto">'+safe(x.sub)+'</span></button>').join(""):'<div class="small muted" style="padding:16px">No matching agents or runs.</div>';
 }
 input.addEventListener("input",update);update();input.focus();
 overlay.querySelector("#searchClose").onclick=()=>overlay.remove();
 overlay.onclick=event=>{if(event.target===overlay)overlay.remove();};
 overlay.addEventListener("click",event=>{
  const action=event.target.closest("[data-search-action]");
  if(!action)return;
  const id=action.dataset.searchId,kind=action.dataset.searchAction;overlay.remove();
  if(kind==="project"){chooseProject(id).catch(e=>notify(e.message));}else navigate("/app/runs/"+id);
 });
}
async function show(){
 stopStream();page.innerHTML='<div class="small muted">Loading…</div>';
 const pathname=location.pathname;
 if(pathname==="/app"){await overview();return;}
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
 const match=pathname.match(/^\/app\/runs\/(app-[0-9a-f]{16}|demo-python-2026-11-07)$/);
 if(match){await showRun(match[1]);return;}
 navigate("/app",true);
}
document.addEventListener("click",async event=>{
 const nav=event.target.closest("a[data-nav]");
 if(nav){event.preventDefault();navigate(nav.pathname+nav.search);return;}
 const button=event.target.closest("[data-action]");if(!button)return;
 const action=button.dataset.action,id=button.dataset.id;
 try{
  if(action==="new-agent"){state.wizard=null;navigate("/app/agents/new");}
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
   state.wizard=null;
   await flow();
   el("repository").value="https://github.com/"+project.repository;
   el("revision").value=project.revision;
   el("sourceDirectory").value=project.directory||"";
   el("advancedImport").open=true;
   el("sourceDirectory").focus();
  }
  else if(action==="run")navigate("/app/runs/"+id);
  else if(action==="project")await chooseProject(id);
  else if(action==="remove"){
   if(!confirm("Delete this imported source snapshot from your workspace? Existing run evidence is retained."))return;
   await req("/projects/"+id+"/remove",{});await agents();
  }else if(action==="flow-back"){state.wizard=null;await flow();}
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
    const fields=["format","mode",field,"args","cases","instruction_env","instruction_base"];
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
  else if(action==="evidence-download"||action==="artifact-download")await download(id,action==="evidence-download"?"evidence":"artifact");
  else if(action==="tab"){state.tab=button.dataset.tab;const runId=location.pathname.split("/").pop();await showRun(runId);}
  else if(action==="signout"){await req("/logout",{});location.assign("/");}
 }catch(e){notify(e.message);}
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
document.addEventListener("keydown",event=>{
 if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();searchOverlay();}
 if(event.key==="Escape")el("searchOverlay")?.remove();
});
window.addEventListener("popstate",()=>show().catch(e=>notify(e.message)));
(async()=>{
 try{
  const session=await req("/session");
  if(session.mode!=="account"){throw Error("Account session endpoint unavailable.");}
  state.username=session.username||null;
  state.guest=!state.username;
  if(state.guest){
    el("avatar").textContent="G";el("avatar").title="Guest · read-only";
    const button=document.createElement("a");button.href="/login?next="+encodeURIComponent(location.pathname);
    button.className="btn compact";button.textContent="Sign in";
    el("avatar").before(button);
    await refreshWorkspace();
  }else el("avatar").textContent=state.username.charAt(0).toUpperCase();
  await show();
 }catch(e){notify(e.message);}
})();