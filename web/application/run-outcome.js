"use strict";
// Pure, evidence-backed interpretation for the Refit review UI.
// UI labels do not authorize export, infer tool calls, or manufacture scores.
(function(root){
 const terminal=status=>!["running","cancelling"].includes(status);
 const phaseLabels={
  train:"Training",training:"Training",validation:"Validation",holdout:"Holdout",
  fresh_export:"Fresh export",source_training:"Original training",
  target_training:"Replacement training",source_validation:"Original validation",
  source_holdout:"Original holdout",original_holdout:"Replacement holdout"
 };
 const phaseName=value=>phaseLabels[value]||String(value||"Evaluation").replaceAll("_"," ");
 const eventLabels={phase_started:"Evaluation phase started",phase_completed:"Evaluation phase finished",
  runtime_ready:"Runtime prepared",sandbox_starting:"Starting sandbox",sandbox_started:"Sandbox started",
  inference_requested:"Model request sent",inference_completed:"Model response received",
  case_completed:"Case completed",sandbox_cleanup:"Sandbox cleanup recorded",
  run_started:"Migration started",terminal:"Run finished"};
 const eventLabel=value=>eventLabels[value]||String(value||"Unknown activity").replaceAll("_"," ");
 const caseEvents=events=>(Array.isArray(events)?events:[]).filter(e=>e?.type==="case_completed"&&e.details&&e.details.phase!=="fresh_export");
 const keyOf=event=>String(event.details.phase||"unknown")+"\u0000"+String(event.details.case||"unknown");
 function pairs(run,events){
  const rows=new Map();
  for(const event of caseEvents(events)){
   const key=keyOf(event),details=event.details;
   if(!rows.has(key))rows.set(key,{key,name:details.case||"Unnamed case",phase:details.phase||"unknown",source:null,target:null,adapted:null});
   const row=rows.get(key);
   if(details.model===run.source){row.source={details,seq:event.seq};}
   else if(details.model===run.target){if(details.adapted){row.adapted={details,seq:event.seq};}else{row.target={details,seq:event.seq};}}
  }
  return [...rows.values()].map(row=>{
   const source=row.source?.details,target=row.target?.details,adapted=row.adapted?.details;
   let status="pending";
   if(source?.passed===false)status="source_failed";
   else if(source?.passed===true && target?.passed===false)status="regression";
   else if(source?.passed===true && target?.passed===true)status="both_passed";
   else if(target?.passed===false)status="target_failed";
   // Difference in output hashes is not automatically a behavioral failure:
   // expected structured, tool and file-state assertions determine correctness.
   return {...row,status,sourcePassed:source?.passed,targetPassed:target?.passed,
    adaptedPassed:adapted?.passed,
    identicalOutput:!!source?.stdout_sha256&&source.stdout_sha256===target?.stdout_sha256};
  });
 }
 const isObservedFailure=row=>["regression","source_failed","target_failed"].includes(row.status);
 function lastEvent(events){
  return (Array.isArray(events)?events:[]).filter(e=>e?.type).at(-1)||null;
 }
 function stage(events){
  const ordered=Array.isArray(events)?events:[];
  const last=lastEvent(ordered);
  const current=[...ordered].reverse().find(e=>e?.type==="phase_started"||e?.type==="phase_completed");
  const active=current?.details?.phase||last?.details?.phase||null;
  const lastLabel=last?eventLabel(last.type):"Waiting for execution evidence";
  return {phase:active?phaseName(active):null,event:lastLabel,lastType:last?.type||null,
   case:last?.details?.case||null,seq:last?.seq??null};
 }
 function summarize(run,events){
  const rows=pairs(run,events);
  const complete=rows.filter(r=>r.sourcePassed!==undefined&&r.targetPassed!==undefined);
  const regressions=rows.filter(r=>r.status==="regression");
  const baselineFailures=rows.filter(r=>r.status==="source_failed");
  const otherFailures=rows.filter(r=>r.status==="target_failed");
  const bothPassed=complete.filter(r=>r.status==="both_passed").length;
  const total=complete.length;
  const active=!terminal(run.status);
  const verification=Array.isArray(run.verification)?run.verification:[];
  const rejectedVerification=verification.findIndex(v=>v.passed===false);
  const cleanupEvents=(Array.isArray(events)?events:[]).filter(e=>e?.type==="sandbox_cleanup");
  const invalidCleanup=cleanupEvents.find(e=>e.details?.receipt?.verified===false);
  let kind="unverified",title="Review the recorded outcome",description="The available evidence does not establish a verified migration.";
  if(active){
   kind="running";title=run.status==="cancelling"?"Cancellation requested":"Migration in progress";
   description="Refit is executing the imported application. Results appear as the original runtime reports them.";
  }else if(run.status==="compatible_on_sample"){
   kind="compatible";title="Compatible on evaluated cases";
   description="The replacement met the recorded requirements. No adaptation was necessary. This is not a guarantee for untested behavior.";
  }else if(run.status==="verified_adaptation"){
   kind="repaired";title="Adaptation verified";
   description="The recorded adaptation passed the required checks. Inspect the change and the fresh original-runtime verification.";
  }else if(run.status==="source_baseline_insufficient"){
   kind="blocked";title="Original baseline failed";
   description="The original agent did not satisfy its required checks. The model comparison cannot establish a valid migration.";
  }else if(run.status==="export_failed_original_runner_verification"){
   kind="blocked";title="Fresh export verification failed";
   description="The proposed configuration failed in the original runtime. No verified export is available.";
  }else if(run.status==="cancelled"){
   kind="blocked";title="Migration cancelled";
   description="The run was cancelled. Completed observations remain available, but no verified migration is established.";
  }else if(run.status==="interrupted"){
   kind="blocked";title="Execution interrupted";
   description="The recorded run stopped before completing its verification requirements.";
  }else if(run.status==="inference_budget_exhausted"){
   kind="blocked";title="Inference budget exhausted";
   description="The run reached its authorized request ceiling before satisfying the verification gates.";
  }else if(run.status==="failed"){
   kind="blocked";title="Migration not verified";
   description="The run failed or its checks were not satisfied. Open the recorded evidence before changing the configuration.";
  }
  // A verified status alone is not authority to display a download.
  const exportState=run.export_available===true?"available":active?"pending":"withheld";
  const issue=regressions[0]||baselineFailures[0]||otherFailures[0];
  let focus=null;
  if(issue){
   const observation=issue.status==="source_failed"?issue.source:issue.target||issue.source;
   focus={type:"case",key:"case-"+observation.seq,title:issue.name,
     detail:phaseName(issue.phase)+" · "+(issue.status==="regression"?"replacement failed":issue.status==="source_failed"?"original failed":"replacement check failed"),
     status:issue.status};
  }else if(rejectedVerification>=0){
   focus={type:"verification",key:"verification-"+rejectedVerification,
    title:verification[rejectedVerification].case||"Failed fresh export check",detail:"Fresh export verification failed",status:"failed"};
  }else if(invalidCleanup){
   focus={type:"cleanup",key:"cleanup-"+invalidCleanup.seq,title:"Sandbox cleanup receipt",detail:"Cleanup was not verified",status:"failed"};
  }else if(verification.length){
   focus={type:"verification",key:"verification-0",title:verification[0].case||"Fresh export verification",
    detail:"Inspect the original-runtime check",status:"observed"};
  }else if(rows.length){
   const item=rows.find(r=>r.target)||rows[0],obs=item.target||item.source;
   if(obs)focus={type:"case",key:"case-"+obs.seq,title:item.name,detail:phaseName(item.phase)+" · Recorded result",status:item.status};
  }
  return {kind,title,description,exportState,rows,regressions,baselineFailures,otherFailures,
   bothPassed,total,completed:rows.length,verificationCount:verification.length,
   verificationPassed:verification.filter(v=>v.passed===true).length,
   cleaned:cleanupEvents.filter(e=>e.details?.receipt?.verified===true).length,
   cleanupCount:cleanupEvents.length,stage:stage(events),focus,active,
   failedCount:rows.filter(isObservedFailure).length};
 }
 root.RefitOutcomes={summarize,pairs,stage,phaseName,eventLabel};
 if(typeof module==="object"&&module.exports)module.exports=root.RefitOutcomes;
})(typeof globalThis!=="undefined"?globalThis:this);
