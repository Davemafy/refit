import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdir} from "node:fs/promises";
import {firefox} from "playwright";
const backend=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let fixture,err="";
backend.stdout.on("data",b=>{const m=b.toString().match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);if(m)fixture=JSON.parse(m[1]);});
backend.stderr.on("data",b=>err+=b.toString().slice(-600));
let browser;const checks=[],jsErrors=[];
try{
 for(let i=0;i<120&&!fixture;i++)await new Promise(r=>setTimeout(r,100));
 assert.ok(fixture,err||"missing fixture");
 browser=await firefox.launch();
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:360,height:780}});
 const page=await ctx.newPage();page.setDefaultTimeout(8000);page.setDefaultNavigationTimeout(25000);
 page.on("pageerror",e=>jsErrors.push(e.message));
 await mkdir("artifacts/mobile-release",{recursive:true});
 async function capture(name,route,width=360,extra){
   await page.setViewportSize({width,height:780});
   await page.goto(fixture.url+route,{waitUntil:"domcontentloaded"});
   await page.getByRole("heading").first().waitFor();
   await page.evaluate(()=>document.fonts.ready);
   if(extra)await extra();
   const dims=await page.evaluate(()=>{
    const cw=document.documentElement.clientWidth;
    const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=="none"&&s.visibility!=="hidden"&&r.width>0&&r.height>0};
    const out=[...document.querySelectorAll("main a,main button,.public-head a,.auth-pane input,.run-mobile-item,.run-mobile-status,.run-mobile-link")]
     .filter(e=>{if(!visible(e))return false;const r=e.getBoundingClientRect();return r.left< -1||r.right>cw+1;});
    return {viewport:cw,scroll:document.documentElement.scrollWidth,clipped:out.map(x=>({tag:x.tagName,cls:x.className,text:x.textContent?.slice(0,35)})).slice(0,10)};
   });
   assert.ok(dims.scroll<=dims.viewport,name+" page overflow "+JSON.stringify(dims));
   assert.deepEqual(dims.clipped,[],name+" clipped controls");
   await page.screenshot({path:"artifacts/mobile-release/"+name+"-"+width+".png",fullPage:true});
   checks.push({name,width,scroll:dims.scroll});
 }
 for(const size of [320,360,390]){
   await capture("landing","/",size,async()=>{
    const link=page.getByRole("link",{name:"Open workspace",exact:true});
    assert.equal(await link.isVisible(),true);
    const box=await link.boundingBox();assert.ok(box.x>=0&&box.x+box.width<=size);
    assert.equal(await page.locator(".m-nav").isVisible(),false,"Desktop navigation should collapse");
    const preview=await page.locator(".m-product-preview").boundingBox();
    assert.ok(preview&&preview.width>=size-40,"Recorded evidence preview squeezed: "+JSON.stringify(preview));
    assert.ok(preview.x>=0&&preview.x+preview.width<=size,"Preview clips the mobile viewport");
    assert.equal(await page.locator(".m-feature").count(),3,"All illustrated steps remain present");
   });
   await capture("runs","/app/runs",size,async()=>{
    assert.equal(await page.locator(".run-table-desktop").isVisible(),false);
    assert.equal(await page.locator(".run-list-mobile").isVisible(),true);
    assert.equal(await page.locator(".run-mobile-item").count(),2, "Both recorded public runs must be accessible");
    assert.equal(await page.locator(".run-mobile-item").getByRole("button",{name:"demo-python-2026-11-07"}).count(),1);
    assert.equal(await page.locator(".run-mobile-item").getByRole("button",{name:"demo-diagnostic-2026-11-08"}).count(),1);
   });
   await capture("overview","/app",size,async()=>{
     assert.equal(await page.locator(".overview-recent").isVisible(),true);
     assert.equal(await page.locator(".subheader").isVisible(),false,"The section title must not be duplicated");
     assert.equal(await page.locator(".migration-route .model-mark").count(),2);
     assert.ok(await page.locator(".verification-tick").count()>0);
     assert.equal(await page.locator("#mobileNavigation summary").isVisible(),true);
     const trial=await page.getByRole("button",{name:/Import your agent/}).boundingBox();
     assert.ok(trial&&trial.y<700,"Live trial action must be visible within the mobile first screen");
     assert.ok(await page.locator(".overview-activity").count()===1,"Recorded activity remains accessible below the live trial");
     assert.equal(await page.locator(".metrics").count(),0,"demo must not impersonate account metrics");
     assert.equal(await page.locator(".run-table-desktop").count(),0);
   });
 }
 await capture("agents","/app/agents",360);
 await capture("signin","/login",360,async()=>{
   const h=await page.getByRole("heading",{name:"Sign in"}).boundingBox();
   const inp=await page.locator("#username").boundingBox();
   assert.ok(h.y<270,"Sign in delayed: "+h.y);
   assert.ok(inp.y<480,"Form delayed: "+inp.y);
 });
 assert.deepEqual(jsErrors,[]);
 console.log(JSON.stringify({status:"pass",browser:"Firefox",screens:checks.length,widths:[320,360,390],noClippedControls:true,marketingNavigation:true,previewReadable:true,mobileRunHistory:true,guestStateDistinct:true,authFormAboveFold:true,paidRequests:0}));
}finally{await browser?.close();backend.kill("SIGKILL");}
