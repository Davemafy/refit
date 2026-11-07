import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
import {gunzipSync} from "node:zlib";

const require=createRequire(import.meta.url);
const outcome=require("../web/application/run-outcome.js");
const archived=JSON.parse(gunzipSync(readFileSync("data/evaluations/application-browser-generic-2026-11-07.json.gz")));
const accepted=outcome.summarize({...archived.run,export_available:true},archived.events);
assert.equal(accepted.kind,"compatible");
assert.equal(accepted.title,"Compatible on evaluated cases");
assert.equal(accepted.exportState,"available");
assert.equal(accepted.total,3);
assert.equal(accepted.bothPassed,3);
assert.equal(accepted.failedCount,0);
assert.equal(accepted.verificationCount,1);
assert.equal(accepted.verificationPassed,1);
assert.equal(accepted.cleanupCount,7);
assert.equal(accepted.cleaned,7);
assert.equal(accepted.rows.filter(x=>x.phase==="train").length,1);
assert.equal(accepted.focus.key,"verification-0");
assert.equal(accepted.stage.lastType,"terminal");

const events=[
 {seq:1,type:"phase_started",details:{phase:"train"}},
 {seq:2,type:"case_completed",details:{phase:"train",case:"order",model:"source",passed:true,stdout_sha256:"aaa"}},
 {seq:3,type:"case_completed",details:{phase:"train",case:"order",model:"target",passed:false,stdout_sha256:"bbb",verdict:{required_tool_observed:false}}},
 {seq:4,type:"phase_completed",details:{phase:"train"}},
 {seq:5,type:"case_completed",details:{phase:"validation",case:"order",model:"source",passed:true,stdout_sha256:"aaa"}},
 {seq:6,type:"case_completed",details:{phase:"validation",case:"order",model:"target",passed:true,stdout_sha256:"bbb"}}
];
const regression=outcome.summarize({status:"failed",source:"source",target:"target",export_available:false},events);
assert.equal(regression.kind,"blocked");
assert.equal(regression.total,2);
assert.equal(regression.bothPassed,1);
assert.equal(regression.regressions.length,1);
assert.equal(regression.rows.length,2,"the same case name in different phases must not collapse");
assert.equal(regression.focus.key,"case-3");
assert.equal(regression.exportState,"withheld");
assert.equal(regression.rows.find(x=>x.phase==="validation").status,"both_passed",
 "Different output hashes do not imply failure when both assertion sets pass");
const active=outcome.summarize({status:"running",source:"source",target:"target"},[{seq:10,type:"phase_started",details:{phase:"validation"}}]);
assert.equal(active.kind,"running");
assert.equal(active.total,0);
assert.equal(active.exportState,"pending");
assert.equal(active.stage.phase,"Validation");
assert.equal(active.stage.event,"Evaluation phase started");
const baseline=outcome.summarize({status:"source_baseline_insufficient",source:"source",target:"target"},[
 {seq:1,type:"case_completed",details:{phase:"train",case:"x",model:"source",passed:false}}
]);
assert.equal(baseline.kind,"blocked");
assert.equal(baseline.focus.key,"case-1");
const repaired=outcome.summarize({status:"verified_adaptation",source:"source",target:"target",export_available:true},events);
assert.equal(repaired.kind,"repaired");
assert.equal(repaired.exportState,"available");
assert.equal(repaired.regressions.length,1);
const noExport=outcome.summarize({status:"compatible_on_sample",source:"source",target:"target",export_available:false},events);
assert.equal(noExport.exportState,"withheld","never infer artifact availability from a compatible status");
const interrupted=outcome.summarize({status:"interrupted",source:"source",target:"target"},[]);
assert.equal(interrupted.title,"Execution interrupted");
assert.equal(interrupted.focus,null);
const verification=outcome.summarize({status:"export_failed_original_runner_verification",source:"source",target:"target",verification:[{case:"replay",passed:false}]},[]);
assert.equal(verification.focus.key,"verification-0");
const cleanup=outcome.summarize({status:"failed",source:"source",target:"target"},[{seq:7,type:"sandbox_cleanup",details:{receipt:{verified:false}}}]);
assert.equal(cleanup.focus.key,"cleanup-7");
assert.deepEqual(outcome.pairs({source:"source",target:"target"},[]),[]);
console.log(JSON.stringify({status:"pass",fixture_cases:accepted.total,tests:["archived","regression","duplicate-names","running","baseline","repair","gating","interruption","verification","cleanup","empty"]}));
