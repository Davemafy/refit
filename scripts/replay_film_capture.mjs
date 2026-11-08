import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {spawn} from "node:child_process";
import {chromium} from "playwright";

const output=path.resolve("artifacts/refit-replay-film");
fs.mkdirSync(output,{recursive:true});
const fixture=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let base="",errors="",browser,raw;
fixture.stdout.on("data",chunk=>{const match=chunk.toString().match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);if(match)base=JSON.parse(match[1]).url});
fixture.stderr.on("data",chunk=>{errors+=chunk.toString()});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
try{
  for(let i=0;i<200&&!base;i++)await sleep(100);
  assert.ok(base,"Local application fixture unavailable: "+errors.slice(-600));
  browser=await chromium.launch({headless:true});
  const ctx=await browser.newContext({viewport:{width:1920,height:1080},screen:{width:1920,height:1080},
    ignoreHTTPSErrors:true,colorScheme:"dark",recordVideo:{dir:output,size:{width:1920,height:1080}}});
  const page=await ctx.newPage();
  await page.addInitScript(()=>{
    window.addEventListener("DOMContentLoaded",()=>{
      if(document.querySelector("#replay-film-pointer"))return;
      const pointer=document.createElement("span");pointer.id="replay-film-pointer";
      pointer.setAttribute("aria-hidden","true");
      pointer.style.cssText="position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transform:translate(-150px,-150px);filter:drop-shadow(0 5px 4px #0009)";
      pointer.innerHTML='<svg width="30" height="36" viewBox="0 0 30 36" xmlns="http://www.w3.org/2000/svg"><path d="M3 2v28l7-7 6 11 5-3-6-10 10-2Z" fill="#fff" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>';
      document.body.appendChild(pointer);
      document.addEventListener("mousemove",e=>{pointer.style.transform="translate("+e.clientX+"px,"+e.clientY+"px)";},{passive:true});
    });
  });
  const failure=[];
  page.on("pageerror",e=>failure.push(e.message));
  await page.goto(base+"/app/replay?studio=1&autoplay=1",{waitUntil:"domcontentloaded",timeout:30000});
  await page.locator("#replayScreen").waitFor();
  await page.waitForTimeout(1200);
  const captureStart=Date.now();
  const step=page.locator("[data-replay-index]");
  const count=await step.count();
  assert.ok(count>20,"Need enough real recorded agent steps");
  await page.screenshot({path:path.join(output,"shot-01-opening.png")});
  // Actual motion, not a simulated response: cursor tracks clicked source events.
  async function moveClick(locator){
    const r=await locator.boundingBox();if(!r)return;
    await page.mouse.move(r.x+r.width*.20,r.y+r.height*.5,{steps:22});
    await sleep(220);
    await page.mouse.move(r.x+r.width*.52,r.y+r.height*.50,{steps:15});
    await sleep(160);
    await locator.click();
  }
  await sleep(6500);
  await moveClick(step.nth(Math.min(14,count-1)));
  await sleep(5200);
  const caseIndex=await page.locator("[data-replay-index]").evaluateAll(nodes=>{
    return nodes.findIndex(node=>node.textContent.includes("Agent case evaluated"));
  });
  if(caseIndex>=0)await moveClick(step.nth(caseIndex));
  await sleep(5500);
  const modelIndex=await page.locator("[data-replay-index]").evaluateAll(nodes=>{
    return nodes.findIndex(node=>node.textContent.includes("Model response"));
  });
  if(modelIndex>=0)await moveClick(step.nth(modelIndex));
  await sleep(5600);
  await page.screenshot({path:path.join(output,"shot-02-model-response.png")});
  await moveClick(page.locator("#replayPlay"));
  await sleep(6200);
  await moveClick(page.locator("#replayPlay"));
  const cleanupIndex=await page.locator("[data-replay-index]").evaluateAll(nodes=>{
    return nodes.findIndex(node=>node.textContent.includes("Worker cleanup"));
  });
  if(cleanupIndex>=0)await moveClick(step.nth(cleanupIndex));
  await sleep(5500);
  await page.screenshot({path:path.join(output,"shot-03-cleanup.png")});
  await page.mouse.move(640,250,{steps:35});
  await sleep(4000);
  fs.writeFileSync(path.join(output,"capture-manifest.json"),JSON.stringify({
    film_source:"immutable recorded Python agent evidence",
    simulated_inference:false,real_sandbox_events:true,events:count,
    full_screen_product_mode:true,onscreen_cursor:"synthetic pointer location, actual DOM clicks",
    elapsed_seconds:Number(((Date.now()-captureStart)/1000).toFixed(2)),
    notes:"The recording uses existing measured event data; no new inference is executed."
  },null,2));
  const video=page.video();
  await page.close();
  raw=await video.path();
  await ctx.close();
  assert.deepEqual(failure,[],"Browser errors");
}finally{
  await browser?.close();
  fixture.kill("SIGKILL");
  if(raw)fs.copyFileSync(raw,path.join(output,"refit-recorded-agent-replay.webm"));
}
console.log("REFIT_REPLAY_FILM_READY",path.join(output,"refit-recorded-agent-replay.webm"));
