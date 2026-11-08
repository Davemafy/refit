import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {chromium} from "playwright";
const server=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let base="",errors="",browser;
server.stdout.on("data",s=>{const m=s.toString().match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);if(m)base=JSON.parse(m[1]).url;});
server.stderr.on("data",s=>{errors+=s.toString();});
try{
 for(let i=0;i<120&&!base;i++)await new Promise(r=>setTimeout(r,100));
 assert.ok(base,"Fixture did not launch: "+errors.slice(-400));
 browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900},ignoreHTTPSErrors:true});
 const pageErrors=[],requests=[];
 page.on("pageerror",e=>pageErrors.push(e.message));
 page.on("request",request=>{
   if(request.method()==="POST"&&request.url().includes("/api/application/try"))requests.push(request.url());
 });
 await page.goto(base+"/app",{waitUntil:"domcontentloaded"});
 const cta=page.getByRole("button",{name:/Run refund agent/i});
 await cta.waitFor({state:"visible"});
 assert.equal(await page.locator('a[href="/app/replay"]').count(),0,"No staged replay links");
 const receipt=page.waitForResponse(response=>
   response.request().method()==="POST"&&response.url().endsWith("/api/application/try-refund"));
 await cta.click();
 const response=await receipt;
 assert.equal(response.status(),202,await response.text());
 const started=await response.json();
 assert.match(started.id,/^app-[0-9a-f]{16}$/);
 assert.equal(started.live,true);
 await page.waitForURL(new RegExp("/app/runs/"+started.id+"$"));
 await page.getByRole("heading",{name:/Executing migration/i}).waitFor();
 const details=await page.request.get(base+"/api/application/runs/"+started.id);
 assert.equal(details.status(),200);
 const run=await details.json();
 assert.equal(run.import.repository,"refit/refund-agent-sample");
 assert.equal(run.source,"deepseek-v4.1-flash-1017");
 assert.equal(run.target,"glm-5.2");
 assert.equal(run.budget,20);
 assert.equal(requests.length,1,"One click starts exactly one authorized run");
 assert.ok(await page.getByRole("button",{name:"Trace",exact:true}).isVisible());
 await page.getByRole("button",{name:"Trace",exact:true}).click();
 assert.match(page.url(),/view=traces/);
 assert.equal((await page.request.get(base+"/app/replay")).status(),401);
 assert.deepEqual(pageErrors,[]);
 await page.setViewportSize({width:390,height:844});
 await page.reload();
 await page.getByRole("heading",{name:/Executing migration/i}).waitFor();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 console.log(JSON.stringify({result:"passed",real_route:"/api/application/try-refund",
   persisted_run:started.id,live:false,requests_dispatched:0,
   note:"Fixture disables actual inference; separate production smoke confirms real model calls."}));
 await page.close();
}finally{await browser?.close();server.kill("SIGKILL");}
