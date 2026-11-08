import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const origin = process.env.REFIT_URL || 'https://80.240.30.92';
const outdir = path.resolve('demo-output');
fs.mkdirSync(outdir, { recursive: true });
const story = [];
// 2560x1440 source, rasterized at high resolution before 1920x1080 delivery.
const viewport = { width: 2560, height: 1440 };
const visualZoom = 4 / 3;
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport, screen: viewport, deviceScaleFactor: 1,
  ignoreHTTPSErrors: true, reducedMotion: 'no-preference', colorScheme: 'dark',
});
const page = await context.newPage();

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const framesDir = path.join(outdir,'frames');
fs.mkdirSync(framesDir,{recursive:true});
let screencast = null, captureFrames = [], captureStarted = 0, captureEnd = 0;
async function startRecording() {
  const cdp = await context.newCDPSession(page);
  screencast = cdp;
  captureStarted = Date.now();
  cdp.on('Page.screencastFrame', frame => {
    const i = captureFrames.length;
    const name = String(i).padStart(6,'0')+'.jpg';
    const file = path.join(framesDir,name);
    fs.writeFileSync(file,Buffer.from(frame.data,'base64'));
    captureFrames.push({file:name, timestamp:frame.metadata.timestamp, receivedAt:Date.now()});
    cdp.send('Page.screencastFrameAck',{sessionId:frame.sessionId}).catch(()=>{});
  });
  await cdp.send('Page.startScreencast',{format:'jpeg',quality:98,maxWidth:2560,maxHeight:1440,everyNthFrame:1});
  mark('recording-start',{sourceWidth:2560,sourceHeight:1440,method:'CDP high-quality frame stream'});
}
async function stopRecording() {
  if(!screencast) return;
  await screencast.send('Page.stopScreencast');
  captureEnd = Date.now();
  await sleep(300);
  if(captureFrames.length < 10)throw Error('High-quality capture produced too few frames');
  const manifest = ['ffconcat version 1.0'];
  for(let i=0;i<captureFrames.length;i++){
    const current=captureFrames[i], next=captureFrames[i+1];
    const duration=next?Math.max(.001,next.timestamp-current.timestamp):
      Math.max(.3,(captureEnd-current.receivedAt)/1000);
    manifest.push("file 'frames/"+current.file+"'");
    manifest.push('duration '+duration.toFixed(6));
  }
  manifest.push("file 'frames/"+captureFrames.at(-1).file+"'");
  fs.writeFileSync(path.join(outdir,'frames.ffconcat'),manifest.join('\n')+'\n');
  fs.writeFileSync(path.join(outdir,'capture-summary.json'),JSON.stringify({
    captureMethod:'Chrome DevTools screencast with high-quality JPEG frames',
    sourceResolution:'2560x1440',outputResolution:'1920x1080',
    jpegQuality:98,sourceFrames:captureFrames.length,
    captureDurationSeconds:((captureEnd-captureStarted)/1000).toFixed(3),
    firstTimestamp:captureFrames[0].timestamp,lastTimestamp:captureFrames.at(-1).timestamp
  },null,2));
  mark('recording-stop',{frames:captureFrames.length});
}

const started = Date.now();
const at = () => (Date.now()-started)/1000;
function mark(label, extra={}) {
  const event = {time:at(),label,...extra};
  story.push(event); console.log(JSON.stringify(event));
}
let pointer = { x: viewport.width/2, y: viewport.height/2 };

async function cursorSetup() {
  await page.evaluate(() => {
    if(document.getElementById('refit-demo-pointer')) return;
    const svg = '<svg width="30" height="38" viewBox="0 0 30 38" xmlns="http://www.w3.org/2000/svg"><path d="M3 2L3 29L10.5 22.7L16.5 35L22.7 31.9L16.6 20.3L26.5 20L3 2Z" fill="#f9fbff" stroke="#1a2028" stroke-width="2.1" stroke-linejoin="round"/></svg>';
    const pointer = document.createElement('div');
    pointer.id='refit-demo-pointer';
    pointer.style.cssText='position:fixed;left:0;top:0;width:30px;height:38px;pointer-events:none;z-index:2147483646;transform:translate(1280px,720px);filter:drop-shadow(0 2px 2px #0008)';
    pointer.innerHTML=svg; document.body.appendChild(pointer);
    const ring=document.createElement('div');ring.id='refit-demo-ring';
    ring.style.cssText='position:fixed;left:0;top:0;width:44px;height:44px;border:1px solid rgba(148,226,207,.85);background:rgba(80,215,185,.13);border-radius:50%;pointer-events:none;opacity:0;z-index:2147483645;transform:translate(1258px,698px) scale(.35);transition:opacity 180ms,transform 380ms cubic-bezier(.19,1,.22,1)';
    document.body.appendChild(ring);
    const style=document.createElement('style');style.id='refit-demo-styles';
    style.textContent='html{scroll-behavior:smooth!important}.shell{will-change:transform;transition:transform 840ms cubic-bezier(.22,1,.36,1)!important}';
    document.head.appendChild(style);
  });
}
async function setPointer(x,y) {
  pointer={x,y}; await page.mouse.move(x,y);
  await page.evaluate(({x,y})=>{
    const p=document.getElementById('refit-demo-pointer');
    if(p)p.style.transform='translate('+x+'px,'+y+'px)';
  },{x,y});
}
async function moveTo(x,y,duration=750) {
  const from={...pointer},dx=x-from.x,dy=y-from.y,dist=Math.hypot(dx,dy);
  const steps=Math.max(12,Math.round(duration/22));
  const bend=Math.min(45,dist*.09)*((Math.round(x+y)%2)?1:-1);
  for(let i=1;i<=steps;i++){
    const t=i/steps, ease=t*t*(3-2*t);
    const side=Math.sin(Math.PI*t)*bend;
    const px=from.x+dx*ease+side*(-dy/(dist||1));
    const py=from.y+dy*ease+side*(dx/(dist||1));
    await setPointer(px,py);await sleep(duration/steps);
  }
}
async function clickAt(locator,label) {
  await locator.waitFor({state:'visible',timeout:11000});
  const b=await locator.boundingBox(); if(!b)throw Error('Invisible locator: '+label);
  const x=b.x+Math.min(b.width*.52,b.width-6),y=b.y+b.height*.5;
  await moveTo(x,y,630); await sleep(250);
  await page.evaluate(({x,y})=>{
    const r=document.getElementById('refit-demo-ring');
    if(!r)return;
    r.style.opacity='1';
    r.style.transform='translate('+(x-22)+'px,'+(y-22)+'px) scale(1)';
  },{x,y});
  await sleep(130);await locator.click({timeout:11000});
  mark('clicked',{target:label,x,y});await sleep(250);
  await page.evaluate(()=>{
    const r=document.getElementById('refit-demo-ring');
    if(r){r.style.opacity='0';r.style.transform=r.style.transform.replace('scale(1)','scale(1.5)');}
  });
}
async function zoomOn(locator,label,scale=1.31) {
  const b=await locator.boundingBox();if(!b)return;
  const x=b.x+b.width/2,y=b.y+b.height/2;
  const dx=Math.max(-230,Math.min(230,(viewport.width/2-x)*0.18));
  const dy=Math.max(-110,Math.min(110,(viewport.height/2-y)*0.12));
  await page.evaluate(({x,y,dx,dy,scale})=>{
    const shell=document.querySelector('.shell');
    if(shell){const z=parseFloat(shell.style.zoom)||1;shell.style.transformOrigin=(x/z)+'px '+(y/z)+'px';shell.style.transform='translate('+(dx/z)+'px,'+(dy/z)+'px) scale('+scale+')';}
  },{x,y,dx,dy,scale});
  mark('zoom-in',{focus:label,scale,x,y}); await sleep(2300);
  await page.evaluate(()=>{
    const shell=document.querySelector('.shell');
    if(shell)shell.style.transform='none';
  });
  mark('zoom-out',{focus:label});await sleep(930);
}
async function safeNav(href,label,hold=2700) {
  await page.evaluate(()=>{
    const s=document.querySelector('.shell');if(s)s.style.transform='none';
  });await sleep(900);
  const el=page.locator('a[data-nav][href="'+href+'"]').first();
  if(await el.count() && await el.isVisible()) {
    await clickAt(el,label);await sleep(hold);await cursorSetup();
    mark('view',{page:label,url:page.url()});return true;
  }
  mark('missing-nav',{label,href});return false;
}

try{
  const response=await page.goto(origin+'/app',{waitUntil:'domcontentloaded',timeout:35000});
  if(!response||response.status()>=400)throw Error('Refit workspace HTTP '+response?.status());
  await page.waitForTimeout(2400);
  // Scale the UI through browser layout/rasterization, not upscaling compressed video.
  await page.evaluate(zoom => {const shell=document.querySelector('.shell');if(shell)shell.style.zoom=String(zoom);},visualZoom);
  await cursorSetup();
  await startRecording();
  mark('open',{url:page.url(),title:await page.title()});await sleep(3000);
  await zoomOn(page.locator('#page'),'workspace overview',1.13);
  await safeNav('/app/agents','Agents',3000);
  await zoomOn(page.locator('#page'),'agent inventory',1.15);
  const review=page.locator('#page button[data-action="run"][data-id="demo-python-2026-11-07"]').first();
  if(await review.count() && await review.isVisible()) {
    await clickAt(review,'Review recorded agent migration');await sleep(3000);
    await zoomOn(page.locator('.page-lead'),'verified migration summary',1.2);
    const trace=page.locator('button[data-action="tab"][data-tab="traces"]').first();
    if(await trace.count() && await trace.isVisible()){
      await clickAt(trace,'Inspect original tool traces');await sleep(2500);
      await zoomOn(page.locator('#runPanel'),'observed execution traces',1.18);
    }
    const evidence=page.locator('button[data-action="tab"][data-tab="evidence"]').first();
    if(await evidence.count() && await evidence.isVisible()){
      await clickAt(evidence,'Inspect verification evidence');await sleep(2500);
      await zoomOn(page.locator('#runPanel'),'independent verification',1.18);
    }
  }
  await safeNav('/app/runs','Runs',3200);
  const runEntry=page.locator('#page button[data-action="run"]').first();
  if(await runEntry.count() && await runEntry.isVisible()) {
    await zoomOn(runEntry,'recorded migration row',1.22);
    await clickAt(runEntry,'Open recorded migration');await sleep(3300);
    await zoomOn(page.locator('#page'),'migration details',1.19);
  } else mark('no-public-run-row');
  await safeNav('/app/evidence','Evidence',3000);
  await zoomOn(page.locator('#page'),'evidence explorer',1.20);
  await safeNav('/app','Overview',2100);
  await sleep(1800);mark('end');
  await page.screenshot({path:path.join(outdir,'final-frame.png')});
}catch(e){
  mark('capture-error',{message:String(e),url:page.url()});
  try{await page.screenshot({path:path.join(outdir,'failure-frame.png')});}catch{}
}finally{
  await stopRecording();await context.close();
  await browser.close();
  fs.writeFileSync(path.join(outdir,'timeline.json'),JSON.stringify(story,null,2));
  if(story.some(e=>e.label==='capture-error'))process.exitCode=1;
}