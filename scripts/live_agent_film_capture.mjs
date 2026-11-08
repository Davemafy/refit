/**
 * One bounded, authentic guest trial on the existing production application.
 * Never simulates model inference or silently retries a paid attempt.
 * Captured cursor is an overlay tracking real Playwright pointer movements,
 * because browser video recordings omit the OS mouse pointer.
 */
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import {chromium} from "playwright";
const origin="https://80.240.30.92";
const out=path.resolve("artifacts/refit-live-trial-film");
fs.mkdirSync(out,{recursive:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const browser=await chromium.launch({headless:true,args:["--disable-dev-shm-usage"]});
const context=await browser.newContext({
  viewport:{width:1920,height:1080},screen:{width:1920,height:1080},
  deviceScaleFactor:1,colorScheme:"dark",ignoreHTTPSErrors:true,
  recordVideo:{dir:out,size:{width:1920,height:1080}}
});
const page=await context.newPage();
page.setDefaultTimeout(12000);
const notes=[];
const log=(kind,data={})=>{const event={kind,elapsed:Date.now(),...data};notes.push(event);console.log(JSON.stringify(event));};
await page.addInitScript(()=>{
  window.addEventListener("DOMContentLoaded",()=>{
    if(document.getElementById("refit-recording-cursor"))return;
    const overlay=document.createElement("div");
    overlay.id="refit-recording-cursor";
    overlay.setAttribute("aria-hidden","true");
    overlay.style.cssText="position:fixed;top:0;left:0;transform:translate(-100px,-100px);z-index:2147483647;pointer-events:none;width:28px;height:34px;filter:drop-shadow(0 3px 5px #000b);will-change:transform";
    overlay.innerHTML='<svg width="28" height="34" viewBox="0 0 28 34" xmlns="http://www.w3.org/2000/svg"><path d="M3 2v26l6.7-6.6 5.9 11 5.1-2.7-5.9-10.8 9.3-.8Z" fill="#f5f7f3" stroke="#121715" stroke-width="2.1" stroke-linejoin="round"/></svg>';
    document.body.appendChild(overlay);
    document.addEventListener("mousemove",e=>{overlay.style.transform="translate("+e.clientX+"px,"+e.clientY+"px)";},{passive:true});
  });
});
async function moveTo(locator){
  const rect=await locator.boundingBox();
  if(!rect)return;
  await page.mouse.move(rect.x+rect.width*.18,rect.y+rect.height*.65,{steps:16});
  await sleep(220);
  await page.mouse.move(rect.x+rect.width*.57,rect.y+rect.height*.45,{steps:14});
  await sleep(270);
}
let raw,terminal=false;
try{
  const initial=await page.goto(origin+"/app",{waitUntil:"domcontentloaded",timeout:30000});
  assert.equal(initial?.status(),200,"Public Refit workspace inaccessible");
  const start=page.getByRole("button",{name:/Try a live migration/i}).first();
  await start.waitFor({state:"visible",timeout:30000});
  await sleep(2500);
  await page.screenshot({path:path.join(out,"01-live-start.png")});
  await moveTo(start);
  const responsePromise=page.waitForResponse(response=>
    response.request().method()==="POST"&&new URL(response.url()).pathname==="/api/application/try",
    {timeout:25000});
  await start.click();
  const response=await responsePromise;
  const body=await response.json().catch(()=>({}));
  if(response.status()!==202){
    log("live_trial_unavailable",{status:response.status(),reason:body.error?.code||"unknown"});
    await page.screenshot({path:path.join(out,"trial-unavailable.png")});
    throw Error("Live visitor trial not available: "+response.status()+" "+(body.error?.code||""));
  }
  assert.match(body.id,/^app-[0-9a-f]{16}$/);
  log("live_trial_started",{run_id:body.id,budget:body.budget,status:body.status});
  await page.waitForURL(new RegExp("/app/runs/"+body.id+"(?:\\?|$)"),{timeout:20000});
  await sleep(1500);
  const trace=page.locator('button[data-tab="traces"]');
  if(await trace.count()) {await moveTo(trace);await trace.click();log("opened_original_execution_trace");}
  const started=Date.now();
  let lastCount=0;
  while(Date.now()-started<145000){
    const request=await page.request.get(origin+"/api/application/runs/"+body.id,{timeout:7000}).catch(()=>null);
    if(request?.ok()){
      const run=await request.json();
      terminal=!["queued","running","cancelling"].includes(run.status);
      log("observed_run_status",{status:run.status,model_requests:run.model_requests});
    }
    const list=page.locator(".trace-entry");
    const count=await list.count().catch(()=>0);
    if(count>lastCount){
      lastCount=count;
      await list.last().scrollIntoViewIfNeeded({timeout:1000}).catch(()=>{});
      await moveTo(list.last()).catch(()=>{});
      await list.last().click({timeout:1000}).catch(()=>{});
    }
    if(Date.now()-started>12000&&Date.now()-started<15000)await page.screenshot({path:path.join(out,"02-execution-trace.png")});
    if(terminal&&Date.now()-started>23000)break;
    await sleep(3100);
  }
  await page.screenshot({path:path.join(out,"03-result.png")});
  await sleep(2200);
  const evidence=page.locator('button[data-tab="evidence"]');
  if(await evidence.count()){await moveTo(evidence);await evidence.click();await sleep(2500);}
  await page.screenshot({path:path.join(out,"04-evidence.png")});
  await sleep(1700);
  fs.writeFileSync(path.join(out,"live-run-manifest.json"),JSON.stringify({
    run_id:body.id,real_model_run:true,
    new_paid_trial_started_once:true,was_terminal:terminal,
    source:"Real Refit guest trial with Vultr inference; never a simulated replay",
    events:notes
  },null,2));
}finally{
  const video=page.video();
  await page.close();
  raw=await video.path();
  await context.close();
  await browser.close();
  if(raw)fs.copyFileSync(raw,path.join(out,"refit-real-agent-run.webm"));
}
console.log("REAL_AGENT_RUN_CAPTURE_COMPLETE",path.join(out,"refit-real-agent-run.webm"));
