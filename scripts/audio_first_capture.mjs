/**
 * Refit: audio-first evidence capture.
 * Records the LIVE, read-only UI and public evidence pages at the 15 exact
 * timestamps of the approved 2:40 soundtrack. No fake app UI or outcomes.
 */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const origin='https://80.240.30.92';
const output=path.resolve('artifacts/audio-first-capture');
fs.mkdirSync(output,{recursive:true});
const scenes=[
  {at:0,    end:9.56,   id:'01-regression',       target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic', action:'inspect', note:'Original vs replacement: show recorded refund evidence; overlay tau2 totals only with report source'},
  {at:9.56, end:15.82,  id:'02-divergence',       target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic', action:'inspect-middle', note:'Tight readable look at execution trace'},
  {at:15.82,end:25.20,  id:'03-introduce-refit',  target:'/app', action:'overview', note:'Actual Refit overview'},
  {at:25.20,end:31.25,  id:'04-agent',            target:'/app/agents', action:'overview', note:'Read-only agent/workflow interface'},
  {at:31.25,end:39.50,  id:'05-baseline',         target:'https://github.com/Davemafy/refit/blob/main/docs/framework-evidence-2026-11-06.md', action:'doc-top', note:'Actual 24/24 source result from separate upstream tau2 evaluation'},
  {at:39.50,end:49.43,  id:'06-regression-detail',target:'https://github.com/Davemafy/refit/blob/main/docs/framework-evidence-2026-11-06.md', action:'inspect-middle', note:'Recorded refund comparison; do not imply identical to separate tau2 report'},
  {at:49.43,end:61.42,  id:'07-diagnosis',        target:'https://github.com/Davemafy/refit/blob/main/docs/live-evidence-2026-11-06.md', action:'inspect-bottom', note:'Genuine recorded patch and comparison'},
  {at:61.42,end:71.23,  id:'08-patch',            target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic', action:'inspect', note:'Review existing exported compatibility artifact'},
  {at:71.23,end:78.67,  id:'09-boundary-bridge', target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic', action:'diagnostic', note:'Actual published Challenge 1 diagnostic'},
  {at:78.67,end:91.18,  id:'10-host-evidence',    target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=containment', action:'containment', note:'Actual Vultr-host containment evidence'},
  {at:91.18,end:107.53, id:'11-denials-cleanup', target:'/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=containment', action:'containment-scroll', note:'Real prohibited actions/cleanup; this is separate from tau2 evaluation'},
  {at:107.53,end:121.13,id:'12-independent',    target:'https://github.com/Davemafy/refit/blob/main/docs/framework-evidence-2026-11-06.md', action:'doc-top', note:'Original tau2 runner and predeclared seeds'},
  {at:121.13,end:132.70,id:'13-score-payoff',   target:'https://github.com/Davemafy/refit/blob/main/docs/framework-evidence-2026-11-06.md', action:'doc-top', note:'Actual source 24/24, unchanged 13/24, patched 24/24 table'},
  {at:132.70,end:146.60,id:'14-rejection',      target:'https://github.com/Davemafy/refit/blob/main/docs/vultr-frozen-patch-recovery-2026-11-06.md', action:'inspect', note:'Separate on-host auto repair candidate rejected at validation'},
  {at:146.60,end:160,   id:'15-refit-outro',     target:'/app', action:'overview', note:'Actual Refit interface before editorial end title'}
];
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const browser=await chromium.launch({headless:true,args:['--disable-dev-shm-usage']});
const context=await browser.newContext({
  viewport:{width:1920,height:1080},
  screen:{width:1920,height:1080},
  deviceScaleFactor:1,
  colorScheme:'dark',
  ignoreHTTPSErrors:true,
  recordVideo:{dir:output,size:{width:1920,height:1080}}
});
const page=await context.newPage();
page.setDefaultTimeout(5000);
const events=[];
const emit=(entry)=>{events.push({...entry,now:new Date().toISOString()});console.log(JSON.stringify(events.at(-1)))};
const address=target=>target.startsWith('http')?target:origin+target;
async function goto(target){
  try{
    const response=await page.goto(address(target),{waitUntil:'domcontentloaded',timeout:22000});
    await page.waitForTimeout(450);
    if(!target.startsWith('http')){
      await page.evaluate(()=>{
        const shell=document.querySelector('.shell');
        if(shell)shell.style.zoom='1.18';
      }).catch(()=>{});
    }
    return response?.status()??0;
  }catch(err){
    emit({event:'navigation_warning',target,message:String(err).slice(0,160)});
    return -1;
  }
}
async function gentleMouse(){
  for (const [x,y] of [[1280,480],[1100,600],[1220,570]]){
    await page.mouse.move(x,y,{steps:10}).catch(()=>{});
    await sleep(250);
  }
}
async function scrollInspector(fraction){
  await page.evaluate((f)=>{
    const node=document.querySelector('.evidence-inspector')||
      document.querySelector('main')||document.scrollingElement;
    if(node) node.scrollTo({top:(node.scrollHeight-node.clientHeight)*f,behavior:'smooth'});
  },fraction).catch(()=>{});
}
async function inspect(action){
  if(action==='containment'||action==='containment-scroll'){
    const b=page.locator('.evidence-index [data-key="containment"]');
    if(await b.count())await b.first().click({timeout:1800}).catch(()=>{});
    await scrollInspector(action==='containment-scroll'?.78:.27);
  }else if(action==='diagnostic'){
    const b=page.locator('.evidence-index [data-key="diagnostic"]');
    if(await b.count())await b.first().click({timeout:1800}).catch(()=>{});
    await scrollInspector(.12);
  }else if(action==='inspect-middle'){
    await scrollInspector(.45);
  }else if(action==='inspect-bottom'){
    await scrollInspector(.77);
  }else if(action==='doc-top'){
    await page.evaluate(()=>window.scrollTo({top:180,behavior:'smooth'})).catch(()=>{});
  }else if(action==='inspect'){
    await scrollInspector(.18);
  }
  await gentleMouse();
}
let recordedPath;
try {
  const deployment=await page.request.get(origin+'/api/application/release');
  assert.equal(deployment.status(),200,'Live release endpoint not available');
  const release=await deployment.json();
  const containment=await page.request.get(origin+'/api/application/containment-proof');
  assert.equal(containment.status(),200,'Live containment evidence unavailable');
  const proof=await containment.json();
  assert.equal(proof.verified,true,'Do not film an unverified containment claim');
  const diagnostic=await page.request.get(origin+'/api/application/challenge1-demo');
  assert.equal(diagnostic.status(),200,'Live diagnostic evidence unavailable');
  await goto('/app'); // Establish read-only guest workspace before recording.
  const original=await goto(scenes[0].target);
  assert.equal(original,200,'Opening published Refit diagnostic unavailable');
  await sleep(5000); // intentional preroll; trimmed to t=0 in final MP4
  const started=Date.now();
  emit({event:'recording_started',revision:release.revision,host_containment_verified:proof.verified});
  let last='';
  for (const scene of scenes){
    const offset=Date.now()-started;
    if(offset<scene.at*1000)await sleep(scene.at*1000-offset);
    let status=200;
    if(scene.target!==last && scene.at!==0)status=await goto(scene.target);
    last=scene.target;
    emit({event:'scene',id:scene.id,at:scene.at,end:scene.end,url:page.url(),status,note:scene.note,elapsed:Number(((Date.now()-started)/1000).toFixed(2))});
    await inspect(scene.action);
    const remaining=scene.end*1000-(Date.now()-started);
    if(remaining>0)await sleep(remaining);
  }
  const left=160000-(Date.now()-started);
  if(left>0)await sleep(left);
  await page.screenshot({path:path.join(output,'final-ui.png')});
  fs.writeFileSync(path.join(output,'scenes.json'),JSON.stringify({duration:160,preroll_seconds:5,release:release.revision,verified_containment:proof.verified,scenes,events},null,2));
}finally{
  const video=page.video();
  await page.close();
  recordedPath=await video.path();
  await context.close();
  await browser.close();
}
fs.copyFileSync(recordedPath,path.join(output,'refit-ui-source.webm'));
console.log('RECORDING COMPLETE',path.join(output,'refit-ui-source.webm'));
