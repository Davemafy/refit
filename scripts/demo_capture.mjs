import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const origin = process.env.REFIT_URL || 'https://80.240.30.92';
const outdir = path.resolve('demo-output');
fs.mkdirSync(outdir, { recursive: true });
const story = [];
const viewport = { width: 1600, height: 900 };
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport, screen: viewport, deviceScaleFactor: 1,
  ignoreHTTPSErrors: true, reducedMotion: 'no-preference', colorScheme: 'dark',
  recordVideo: { dir: outdir, size: viewport } });
const page = await context.newPage();
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
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
    pointer.style.cssText='position:fixed;left:0;top:0;width:30px;height:38px;pointer-events:none;z-index:2147483646;transform:translate(800px,450px);filter:drop-shadow(0 2px 2px #0008)';
    pointer.innerHTML=svg; document.body.appendChild(pointer);
    const ring=document.createElement('div');ring.id='refit-demo-ring';
    ring.style.cssText='position:fixed;left:0;top:0;width:44px;height:44px;border:1px solid rgba(148,226,207,.85);background:rgba(80,215,185,.13);border-radius:50%;pointer-events:none;opacity:0;z-index:2147483645;transform:translate(785px,435px) scale(.35);transition:opacity 180ms,transform 380ms cubic-bezier(.19,1,.22,1)';
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
    if(shell){shell.style.transformOrigin=x+'px '+y+'px';shell.style.transform='translate('+dx+'px,'+dy+'px) scale('+scale+')';}
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
  await page.waitForTimeout(2400);await cursorSetup();
  mark('open',{url:page.url(),title:await page.title()});await sleep(3000);
  await zoomOn(page.locator('#page'),'workspace overview',1.13);
  await safeNav('/app/agents','Agents',3000);
  await zoomOn(page.locator('#page'),'agent inventory',1.15);
  await safeNav('/app/runs','Runs',3200);
  const runEntry=page.locator('#page a[href*="/app/runs/"]').first();
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
  const v=page.video();await context.close();
  if(v)await v.saveAs(path.join(outdir,'raw-capture.webm'));
  await browser.close();
  fs.writeFileSync(path.join(outdir,'timeline.json'),JSON.stringify(story,null,2));
  if(story.some(e=>e.label==='capture-error'))process.exitCode=1;
}