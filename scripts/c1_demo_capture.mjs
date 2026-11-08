/**
 * Reproducible, high-resolution browser recording of ACTUAL published
 * production evidence. Never synthesizes outcomes or sends inference calls.
 * Requires a revision-matched Vultr host containment receipt.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const origin = process.env.REFIT_URL || 'https://80.240.30.92';
const expected = process.env.REFIT_EXPECTED_REVISION || '';
assert.match(expected, /^[0-9a-f]{40}$/, 'Exact deployed SHA required');
const out = path.resolve('artifacts/challenge1-video');
const frames = path.join(out, 'frames');
fs.mkdirSync(frames, {recursive:true});
const viewport = {width:2560,height:1440};
const browser = await chromium.launch({headless:true,args:['--disable-dev-shm-usage']});
const ctx = await browser.newContext({viewport,screen:viewport,colorScheme:'dark',
  reducedMotion:'reduce',ignoreHTTPSErrors:false,deviceScaleFactor:1});
const page = await ctx.newPage();
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
const timeline = [];
let capture = null, recorded = [], ended = 0;
const note = (label,more={}) => {
  const item={at:new Date().toISOString(),label,...more};
  timeline.push(item);console.log(JSON.stringify(item));
};
function attachLabel() {
  return page.evaluate(() => {
    document.querySelector('#c1-recorded-label')?.remove();
    const label=document.createElement('div');
    label.id='c1-recorded-label';
    label.textContent='Recorded production evidence  ·  Refit / Vultr Challenge 1';
    label.style.cssText='position:fixed;bottom:28px;right:32px;z-index:999999;' +
      'background:rgba(13,19,23,.93);border:1px solid rgba(255,255,255,.14);' +
      'color:#e8edf0;font:600 21px system-ui;padding:17px 23px;border-radius:12px;' +
      'box-shadow:0 14px 46px #0008;pointer-events:none;';
    document.body.append(label);
    const shell=document.querySelector('.shell');
    if(shell)shell.style.zoom='1.4';
  });
}
async function beginCapture(){
  capture=await ctx.newCDPSession(page);
  capture.on('Page.screencastFrame',frame=>{
    const idx=recorded.length,name=String(idx).padStart(6,'0')+'.jpg';
    fs.writeFileSync(path.join(frames,name),Buffer.from(frame.data,'base64'));
    recorded.push({name,timestamp:frame.metadata.timestamp});
    capture.send('Page.screencastFrameAck',{sessionId:frame.sessionId}).catch(()=>{});
  });
  await capture.send('Page.startScreencast',{
    format:'jpeg',quality:97,maxWidth:2560,maxHeight:1440,everyNthFrame:1,
  });
  note('recording_started',{source:'production Chromium',resolution:'2560x1440'});
}
async function endCapture(){
  if(!capture)return;
  await capture.send('Page.stopScreencast');ended=Date.now();
  await sleep(350);
  assert(recorded.length>=12,'Missing source video frames');
  const manifest=['ffconcat version 1.0'];
  for(let i=0;i<recorded.length;i++){
    const current=recorded[i],next=recorded[i+1];
    const duration=next?Math.max(.005,next.timestamp-current.timestamp):.5;
    manifest.push("file 'frames/"+current.name+"'");
    manifest.push('duration '+duration.toFixed(6));
  }
  manifest.push("file 'frames/"+recorded.at(-1).name+"'");
  fs.writeFileSync(path.join(out,'frames.ffconcat'),manifest.join('\n')+'\n');
  fs.writeFileSync(path.join(out,'timeline.json'),JSON.stringify(timeline,null,2));
  note('recording_finished',{frames:recorded.length});
}
async function hold(label,ms=2600){
  note(label);
  await sleep(ms);
}
async function scrollInspector(frac,ms=2300){
  await page.locator('.evidence-inspector').evaluate((node,value)=>{
    node.scrollTo({top:(node.scrollHeight-node.clientHeight)*value,behavior:'smooth'});
  },frac);
  await hold('inspector_scroll_'+frac,ms);
}
async function focusEvidence(key){
  const button=page.locator('.evidence-index [data-key="'+key+'"]');
  await button.waitFor({state:'visible'});
  await button.click();
  await hold('selected_'+key,2900);
}
try{
  const getJson=async route=>{
    const resp=await page.request.get(origin+route);
    assert.equal(resp.status(),200,'Expected public endpoint '+route);
    return resp.json();
  };
  const release=await getJson('/api/application/release');
  const migration=await getJson('/api/application/challenge1-demo');
  const proof=await getJson('/api/application/containment-proof');
  assert.equal(release.revision,expected);
  assert.equal(proof.revision,expected);
  assert.equal(migration.recorded,true);
  assert.equal(migration.run.diagnostic.verified,true);
  assert.equal(proof.verified,true);
  assert.equal(proof.generated_by_model,false);
  assert.equal(proof.attempts.length,5);
  assert.ok(proof.attempts.every(x=>x.blocked===true));
  assert.ok(proof.workers.every(x=>x.runtime==='runsc' && x.cleanup_verified===true));
  const link='/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic';
  const response=await page.goto(origin+link,{waitUntil:'domcontentloaded',timeout:35000});
  assert.equal(response.status(),200);
  await page.getByRole('heading',{name:'Vultr-generated Python',exact:true}).waitFor();
  await attachLabel();
  await beginCapture();
  await hold('migration_recorded_verified_and_model_written',4200);
  await scrollInspector(.38,3800);
  await scrollInspector(.74,4200);
  await scrollInspector(1,3300);
  await scrollInspector(0,1600);
  await focusEvidence('containment');
  await page.getByRole('heading',{name:'Prohibited actions observed'}).waitFor();
  await hold('host_probe_actual_denial_observations',4700);
  await scrollInspector(.32,3600);
  await scrollInspector(.88,4900);
  await scrollInspector(0,1500);
  await focusEvidence('diagnostic');
  await hold('independent_verification_and_cleanup',2900);
  await scrollInspector(.66,3200);
  await scrollInspector(0,1500);
  await page.screenshot({path:path.join(out,'proof-frame.png')});
  await hold('final_verified_record',2700);
  fs.writeFileSync(path.join(out,'evidence.json'),JSON.stringify({
    recorded:true,production_revision:expected,
    migration_id:migration.run.production_migration_id,
    generator_model:migration.run.diagnostic.generator_model,
    inference_requests:migration.run.model_requests+migration.run.diagnostic.model_requests,
    primary_cleanup:migration.run.diagnostic.sandbox.container_removed_verified,
    crosscheck_cleanup:migration.run.diagnostic.cross_check.sandbox.container_removed_verified,
    vultr_host_proof_revision:proof.revision,host_attempts:proof.attempts.length,
    host_containment_verified:proof.verified,
  },null,2));
} catch(error){
  note('capture_error',{message:String(error)});
  try{await page.screenshot({path:path.join(out,'failure-frame.png')});}catch{}
  process.exitCode=1;
} finally {
  await endCapture().catch(error=>{console.error(error);process.exitCode=1;});
  await ctx.close();
  await browser.close();
}
