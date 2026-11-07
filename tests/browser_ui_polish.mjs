// Browser design regression: archived real migration, no paid requests or fabricated data.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdir} from "node:fs/promises";
import {firefox} from "playwright";
const server=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let ready;let fatal="";
server.stdout.on("data",c=>{const m=c.toString().match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);if(m)ready=JSON.parse(m[1]);});
server.stderr.on("data",c=>{fatal+=c.toString().slice(-350)});
const errors=[];
let browser;
try{
 for(let i=0;i<100&&!ready;i++)await new Promise(r=>setTimeout(r,100));
 assert.ok(ready,"Local HTTPS fixture did not start: "+fatal);
 browser=await firefox.launch();
 const context=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true,viewport:{width:1440,height:900}});
 const reg=await context.request.post(ready.url+"/api/application/register",{headers:{Origin:ready.url},data:{username:"ui-release-qa",password:"refit-ui-release-test-password"}});
 assert.equal(reg.status(),201);
 const seeded=await (await context.request.get(ready.url+"/__fixture__/seed")).json();
 const page=await context.newPage();
 page.setDefaultTimeout(10_000);
 page.on("pageerror",error=>errors.push(error.message));
 await mkdir("artifacts/saas-ui",{recursive:true});
 await page.goto(ready.url+"/app/runs/"+seeded.id,{waitUntil:"domcontentloaded"});
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 assert.equal(await page.locator(".comparison-scroll").isVisible(),true);
 await page.getByRole("button",{name:"Trace",exact:true}).click();
 await page.locator(".trace-waterfall").waitFor();
 assert.equal(await page.locator(".trace-lane").count(),7,"Every recorded case duration must have one bar");
 assert.equal(await page.locator(".trace-entry").count(),57,"No missing observations from the archived run");
 await page.locator('[data-action="trace-filter"][data-filter="models"]').click();
 assert.equal(await page.locator(".trace-entry").count(),14,"Model filter must show actual requests and responses");
 await page.locator('[data-action="trace-filter"][data-filter="cases"]').click();
 assert.equal(await page.locator(".trace-entry").count(),7);
 await page.locator(".trace-entry").first().click();
 assert.match(await page.locator("#traceInspector").innerText(),/Case completed/);
 await page.locator('[data-action="trace-filter"][data-filter="sandbox"]').click();
 assert.equal(await page.locator(".trace-entry").count(),21,"Sandbox filter includes starting, started and cleanup");
 await page.locator(".trace-entry").first().click();
 assert.match(await page.locator("#traceInspector").innerText(),/Sandbox cleanup|Sandbox started|Starting sandbox/);
 await page.locator('[data-action="trace-filter"][data-filter="all"]').click();
 await page.evaluate(()=>scrollTo(0,0));
 await page.screenshot({path:"artifacts/saas-ui/11-trace-explorer-desktop.png",fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.evaluate(()=>scrollTo(0,0));
 assert.equal(await page.locator(".trace-waterfall-scroll").evaluate(el=>el.scrollWidth>el.clientWidth),false,
  "Mobile timeline must not rely on horizontal scrolling");
 await page.screenshot({path:"artifacts/saas-ui/12-trace-explorer-mobile.png",fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"Mobile trace must not overflow viewport");
 await page.setViewportSize({width:320,height:740});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"320px trace must not overflow");
 assert.equal(await page.locator(".trace-waterfall-scroll").evaluate(el=>el.scrollWidth>el.clientWidth),false,
  "320px timeline must not rely on horizontal scrolling");
 await page.getByRole("button",{name:"Evaluation",exact:true}).click();
 await page.locator(".comparison-mobile").waitFor();
 assert.equal(await page.locator(".comparison-mobile").isVisible(),true);
 assert.equal(await page.locator(".comparison-scroll").isVisible(),false);
 assert.equal(await page.locator(".comparison-mobile-case").count(),3,"Only observed paired cases");
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"320px case comparison must not overflow");
 await page.evaluate(()=>scrollTo(0,0));
 await page.screenshot({path:"artifacts/saas-ui/13-mobile-case-comparison.png",fullPage:true});
 const search=page.locator("#search");
 assert.equal(await search.isVisible(),true,"Search must be available on mobile");
 await search.click();
 const dialog=page.getByRole("dialog",{name:"Search agents and runs"});
 await dialog.waitFor();
 const input=page.locator("#searchInput");
 await input.fill(seeded.id);
 await dialog.locator('[data-search-action="run"]').first().waitFor();
 await input.press("Escape");
 assert.equal(await dialog.count(),0);
 assert.equal(await search.evaluate(el=>el===document.activeElement),true,"Focus returns to search trigger");
 await search.click();
 await page.locator("#searchClose").click();
 assert.equal(await dialog.count(),0);
 await page.route("**/api/application/runs",r=>r.abort("failed"));
 await page.locator('.mobile-nav a[href="/app/runs"]').click();
 await page.getByRole("heading",{name:"Unable to load this view"}).waitFor();
 await page.unroute("**/api/application/runs");
 await page.getByRole("button",{name:"Retry loading"}).click();
 await page.getByRole("heading",{name:"Runs",exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 // The public example is privacy-sanitized: case duration is intentionally
 // omitted, while measured model response durations are preserved.
 const guest=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
 const guestPage=await guest.newPage();
 await guestPage.goto(ready.url+"/app/runs/demo-python-2026-11-07",{waitUntil:"domcontentloaded"});
 await guestPage.getByRole("heading",{name:"Review migration results"}).waitFor();
 await guestPage.getByRole("button",{name:"Trace",exact:true}).click();
 await guestPage.getByText("Model response timeline").waitFor();
 assert.equal(await guestPage.locator(".trace-lane").count(),7);
 assert.equal(await guestPage.locator(".trace-duration-bar.failed").count(),0,
  "Unknown model-call outcome must not be drawn as a failure");
 assert.equal(await guestPage.locator(".trace-waterfall-scroll").evaluate(el=>el.scrollWidth>el.clientWidth),false);
 await guestPage.screenshot({path:"artifacts/saas-ui/14-guest-trace-mobile.png",fullPage:true});
 await guest.close();
 assert.deepEqual(errors,[],"No unhandled browser errors");
 console.log(JSON.stringify({status:"pass",browser:"Firefox",archived_run:seeded.id,
  cases:7,recorded_events:57,models:14,case_pairs:3,desktop:true,mobile_390:true,mobile_320:true,
  mobile_search:true,focus_restored:true,request_recovery:true,paid_requests:0}));
}finally{await browser?.close();server.kill("SIGKILL");}