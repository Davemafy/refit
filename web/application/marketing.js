"use strict";
/* Published sample only: no authentication, mutation, model invocation or fabricated counters. */
(async function hydrateRecordedPreview(){
 const label=(id)=>document.getElementById(id);
 try {
  const result=await fetch("/api/application/demo",{credentials:"omit",cache:"no-store"});
  if(!result.ok)throw Error("Published sample unavailable");
  const sample=await result.json();
  if(sample.public_sample!==true || sample.recorded!==true || !sample.run || !Array.isArray(sample.events))
   throw Error("Published sample provenance missing");
  const {run,events}=sample;
  const cases=events.filter(item=>item.type==="case_completed");
  if(run.id!=="demo-python-2026-11-07" || cases.length===0)throw Error("Unknown public example");
  const passed=cases.filter(item=>item.details?.passed===true).length;
  const failed=cases.filter(item=>item.details?.passed===false).length;
  label("previewSource").textContent=run.source;
  label("previewTarget").textContent=run.target;
  label("previewPassed").textContent=passed;
  label("previewFailed").textContent=failed?failed+" failed":"";
  label("previewState").textContent=run.status==="compatible_on_sample"?
   "Compatible on sample":run.status==="verified_adaptation"?"Verified repair":"Measured";
  const ticks=label("previewTicks");
  ticks.replaceChildren();
  for(const item of cases.slice(0,32)){
   const tick=document.createElement("span");
   tick.className="m-tick "+(item.details?.passed===true?"m-tick--pass":
                            item.details?.passed===false?"m-tick--fail":"m-tick--pending");
   ticks.appendChild(tick);
  }
  ticks.setAttribute("aria-label",passed+" passed, "+failed+" failed among "+cases.length+" recorded case observations");
  const verified=events.filter(item=>item.type==="sandbox_cleanup" && item.details?.receipt?.verified===true).length;
  label("previewProvenance").textContent=cases.length+" observed cases · "+verified+
    " verified cleanups · Published run, Nov 2026";
 } catch {
  label("previewState").textContent="Preview unavailable";
  label("previewPassed").textContent="—";
  label("previewProvenance").textContent="Open the workspace to inspect the published sample when available.";
 }
})();
