// End-to-end SaaS UI acceptance against a local HTTPS fixture. No paid inference.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir } from "node:fs/promises";
import { firefox } from "playwright";

const server=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let browser;
const errors=[];
let ready;
let buf="";
server.stdout.on("data",chunk=>{
 buf+=chunk.toString();
 const match=buf.match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);
 if(match&&!ready)ready=JSON.parse(match[1]);
});
server.stderr.on("data",chunk=>{const data=chunk.toString();if(/Traceback|Error|Exception/.test(data))errors.push(data.slice(0,300));});
async function waitReady(){
 for(let i=0;i<80;i++){
  if(ready)return ready;
  if(server.exitCode!==null)throw Error("Fixture exited: "+errors.join("\n"));
  await new Promise(r=>setTimeout(r,100));
 }
 throw Error("Fixture did not become ready.");
}
const zipMaker='import io,sys,zipfile\nbuffer=io.BytesIO()\nwith zipfile.ZipFile(buffer,"w") as z:\n z.writestr("agent.py", "import os\\nOPENAI_BASE_URL=os.getenv(\\\"OPENAI_BASE_URL\\\")\\nOPENAI_MODEL=os.getenv(\\\"OPENAI_MODEL\\\")\\nif __name__ == \\\"__main__\\\":\\n print(\\\"ok\\\")\\n")\nsys.stdout.buffer.write(buffer.getvalue())';
const zip=execFileSync("python3",["-c",zipMaker]);
const runRequests=[];
await mkdir("artifacts/saas-ui", {recursive:true});
try{
 const {url}=await waitReady();
 browser=await firefox.launch();
 const context=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true,viewport:{width:1440,height:900}});
 const page=await context.newPage();page.setDefaultTimeout(12_000);
 page.on("pageerror",error=>errors.push(error.message));
 page.on("request",request=>{if(request.url().endsWith("/api/application/runs")&&request.method()==="POST")runRequests.push(request.url());});
 await page.goto(url+"/");
 await page.getByRole("heading",{name:/Change the model/}).waitFor();
 await page.screenshot({path:"artifacts/saas-ui/01-landing.png",fullPage:true});
 await page.goto(url+"/app");
 await page.getByRole("heading",{name:"Explore Refit"}).waitFor();
 await page.getByText(/Public, read-only preview/).first().waitFor();
 await page.screenshot({path:"artifacts/saas-ui/00-guest-workspace.png",fullPage:true});
 await page.goto(url+"/app/agents/new");
 await page.getByRole("button",{name:/Inspect this agent/}).click();
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 await page.getByText("python -m src.qa").waitFor();
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 await page.getByRole("heading",{name:"Configure migration"}).waitFor();
 await page.getByRole("button",{name:/View recorded results/}).click();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 assert.equal(await page.locator("#pageError").count(),0,"The run review must not show an application error");
 await page.goto(url+"/app/runs");
 await page.getByRole("button",{name:"demo-python-2026-11-07",exact:true}).waitFor();
 await page.getByRole("button",{name:"demo-python-2026-11-07",exact:true}).click();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 assert.equal(await page.locator("#pageError").count(),0,"The run review must not show an application error");
 await page.getByText(/Public, read-only preview/).first().waitFor();
 const exampleDownload=page.waitForEvent("download");
 await page.getByRole("button",{name:/Export verified configuration/}).first().click();
 const exampleFile=await exampleDownload;
 assert.equal(exampleFile.suggestedFilename(),"demo-python-2026-11-07-artifact.json");
 assert.equal((await context.request.get(url+"/api/application/projects")).status(),401);
 assert.equal((await context.request.get(url+"/api/application/runs")).status(),401);
 await page.goto(url+"/signup");
 await page.getByRole("heading",{name:"Create your account"}).waitFor();
 await page.locator("#username").fill("qa-developer");
 await page.locator("#password").fill("refit-browser-ui-test-password");
 await page.getByRole("button",{name:/Continue/}).click();
 await page.waitForURL(url+"/app");
 await page.getByRole("heading",{name:"Your workspace"}).waitFor();
 const secure=(await context.cookies()).find(x=>x.name==="__Host-refit-session");
 assert.ok(secure?.httpOnly&&secure?.secure&&secure?.sameSite==="Strict");

 await page.getByRole("button",{name:/Import agent/}).first().click();
 await page.waitForURL(url+"/app/agents/new");
 await page.getByRole("heading",{name:"Bring your agent"}).waitFor();
 await page.screenshot({path:"artifacts/saas-ui/07-authenticated-import.png",fullPage:true});
 const mobileSigned=await browser.newContext({
   ignoreHTTPSErrors:true,viewport:{width:390,height:844},
   storageState:await context.storageState()
 });
 const mobileSignedPage=await mobileSigned.newPage();
 await mobileSignedPage.goto(url+"/app/agents/new");
 await mobileSignedPage.getByRole("heading",{name:"Bring your agent"}).waitFor();
 const responsive=await mobileSignedPage.evaluate(()=>({
   overflow:document.documentElement.scrollWidth>innerWidth,
   buttonVisible:!!document.querySelector('#importForm button[type="submit"]')
 }));
 assert.equal(responsive.overflow,false,"Signed-in import must fit mobile viewport");
 assert.equal(responsive.buttonVisible,true);
 await mobileSignedPage.screenshot({path:"artifacts/saas-ui/08-authenticated-import-mobile.png",fullPage:true});
 await mobileSigned.close();
 await page.evaluate(async()=>{
   await Promise.all([document.fonts.load('450 14px Geist'),document.fonts.load('450 12px "Geist Mono"')]);
 });
 const fontState=await page.evaluate(()=>({
   sans:document.fonts.check('450 14px Geist'),
   mono:document.fonts.check('450 12px "Geist Mono"'),
   family:getComputedStyle(document.body).fontFamily,
   overflow:document.documentElement.scrollWidth>innerWidth
 }));
 assert.ok(fontState.sans&&fontState.mono,fontState);
 assert.ok(fontState.family.includes("Geist"),fontState);
 assert.equal((await context.request.get(url+"/assets/run-outcome.js")).status(),200);
 assert.equal((await context.request.get(url+"/assets/spline-sans-latin.woff2")).status(),200);
 await page.evaluate(async()=>{await document.fonts.load('590 32px "Spline Sans"')});
 assert.equal(await page.evaluate(()=>document.fonts.check('590 32px "Spline Sans"')),true);
 for(const fontName of ["geist-sans", "geist-mono"]){
   const response=await context.request.get(url+"/assets/"+fontName+".woff2");
   assert.equal(response.status(),200);
   assert.match(response.headers()["content-type"], /^font\/woff2/);
 }
 assert.equal(fontState.overflow,false,"Import screen must not overflow desktop viewport");
 const repo=page.locator("#repository");
 assert.ok(await repo.isVisible(),"Primary repository URL field must be visible");
 assert.ok(!(await page.locator("#advancedImport").getAttribute("open")),"Advanced fields must start collapsed");
 await page.screenshot({path:"artifacts/saas-ui/05-import-desktop.png",fullPage:true});
 const mobile=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
 const mobilePage=await mobile.newPage();
 await mobilePage.goto(url+"/app/agents/new");
 await mobilePage.getByRole("heading",{name:"Bring your agent"}).waitFor();
 assert.equal(await mobilePage.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"Mobile horizontal overflow");
 await mobilePage.screenshot({path:"artifacts/saas-ui/06-import-mobile.png",fullPage:true});
 await mobile.close();
 await page.getByRole("button",{name:"Upload ZIP"}).click();
 await page.locator("#zip").setInputFiles({name:"agent.zip",mimeType:"application/zip",buffer:zip});
 await page.getByRole("button",{name:/Inspect agent/}).click();
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 await page.locator(".fact .value").filter({hasText:/^python -m agent$/}).waitFor();
 await page.getByLabel("Application boundary").selectOption("0");
 await page.screenshot({path:"artifacts/saas-ui/02-inspection.png",fullPage:true});
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 await page.getByRole("heading",{name:"Configure migration"}).waitFor();
 assert.deepEqual(await page.locator("#source option").allTextContents(),
  ["deepseek-v4.1-flash-1017","glm-5.2"]);
 assert.equal(await page.locator("#entryPoint").inputValue(),"agent");
 const cases=page.locator(".setup-case");
 assert.equal(await cases.count(),3);
 for(const [index,split] of ["train","validation","holdout"].entries()){
  const row=cases.nth(index);
  if (await row.getAttribute("open") === null) await row.locator("summary").first().click();
  await row.getByLabel("Case name").fill(split);
  await row.getByLabel("Agent input").fill("Prompt for "+split);
  await row.getByLabel("Expected output").fill("ok");
 }
 await cases.first().getByText("Application state checks",{exact:true}).click();
 await cases.first().getByLabel("File assertions (JSON array)",{exact:false}).fill('[{"path":"state.json","op":"absent"}]');
 await page.getByRole("button",{name:"Edit JSON"}).click();
 const setup=JSON.parse(await page.locator("#setup").inputValue());
 assert.equal(setup.format,"refit.agent.v1");
 assert.deepEqual(setup.cases[0].state,[{path:"state.json",op:"absent"}]);
 assert.deepEqual(setup.cases.map(item=>item.split),["train","validation","holdout"]);
 await page.getByRole("button",{name:"Use guided setup"}).click();
 assert.equal(await cases.last().getByLabel("Agent input").inputValue(),"Prompt for holdout");
 await page.screenshot({path:"artifacts/saas-ui/03-configure.png",fullPage:true});
 await page.getByRole("button",{name:/Run migration/}).click();
 await page.getByText(/Authorize the inference budget/).waitFor();
 assert.equal(runRequests.length,0,"Missing authorization must not submit inference");

 await page.goto(url+"/app/agents");
 await page.getByRole("heading",{name:"Agents"}).waitFor();
 await page.getByRole("button",{name:/Uploaded ZIP/}).waitFor();

 const seeded=await (await context.request.get(url+"/__fixture__/seed")).json();
 assert.ok(seeded.id.startsWith("app-"));
 await page.goto(url+"/app/runs");
 await page.getByRole("button",{name:seeded.id,exact:true}).waitFor();
 await page.getByRole("button",{name:seeded.id,exact:true}).click();
 await page.waitForURL(url+"/app/runs/"+seeded.id);
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 assert.equal(await page.locator("#pageError").count(),0,"The run review must not show an application error");
 await page.getByText(/Sandbox cleanup receipts/).waitFor();
 assert.equal(await page.locator(".decision-surface.compatible").count(),1);
 assert.equal(await page.locator(".decision-stat strong").first().innerText(),"3 / 3");
 assert.equal(await page.locator(".decision-surface").getByText("Verified artifact available").count(),1);
 await page.screenshot({path:"artifacts/saas-ui/04-review.png",fullPage:true});
 await page.setViewportSize({width:390,height:844});
 const comparison = await page.locator(".comparison-scroll").evaluate(table => ({
   pageFits: document.documentElement.scrollWidth <= innerWidth,
   tableScrolls: table.scrollWidth > table.clientWidth,
 }));
 assert.deepEqual(comparison, {pageFits:true, tableScrolls:true});
 await page.screenshot({path:"artifacts/saas-ui/11-comparison-mobile.png",fullPage:true});
 await page.setViewportSize({width:1440,height:900});
 await page.getByRole("button",{name:"Trace",exact:true}).click();
 await page.locator(".log").waitFor();
 await page.getByRole("button",{name:"Evidence",exact:true}).last().click();
 await page.getByRole("navigation",{name:"Run evidence"}).waitFor();
 await page.locator(".evidence-entry").first().click();
 await page.locator("#evidenceInspector").getByText("Fresh export check").first().waitFor();
 await page.getByRole("button",{name:/magnetic-divergence/}).first().click();
 await page.locator("#evidenceInspector").getByText("Tool observations").waitFor();
 await page.locator(".evidence-entry").filter({hasText:"Cleanup receipt"}).first().click();
 await page.locator("#evidenceInspector").getByText("Cleanup reason").waitFor();
 assert.equal(await page.locator("#pageError").count(),0,"Evidence inspection must not show an application error");
 await page.screenshot({path:"artifacts/saas-ui/09-evidence-desktop.png",fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"Evidence inspector must fit mobile viewport");
 await page.screenshot({path:"artifacts/saas-ui/10-evidence-mobile.png",fullPage:true});
 await page.setViewportSize({width:1440,height:900});

 const waiting=page.waitForEvent("download");
 await page.getByRole("button",{name:/Export verified configuration/}).first().click();
 const downloaded=await waiting;
 assert.ok(downloaded.suggestedFilename().endsWith("-artifact.json"));
 assert.equal(runRequests.length,0,"Fixture UI test must never launch inference");

 const failedSeed=(await (await context.request.get(url+"/__fixture__/seed-failure")).json()).id;
 await page.goto(url+"/app/runs/"+failedSeed);
 await page.getByRole("heading",{name:"Migration not verified"}).waitFor();
 await page.getByText("Replacement regression").waitFor();
 assert.equal(await page.locator(".decision-surface.blocked").count(),1);
 assert.equal(await page.locator("#pageError").count(),0,"Rejected run must render without errors");
 assert.equal(await page.getByRole("button",{name:/Export verified configuration/}).count(),0,
   "A failed migration must not offer an export");
 await page.getByRole("button",{name:/Inspect failing evidence/}).click();
 await page.getByRole("navigation",{name:"Run evidence"}).waitFor();
 assert.equal(await page.locator(".evidence-entry.selected").count(),1,
   "First failing case must be selected in the evidence explorer");
 await page.locator("#evidenceInspector").getByText("Failed").first().waitFor();
 await page.screenshot({path:"artifacts/saas-ui/11-rejected-run.png",fullPage:true});
 assert.equal(await page.locator("#pageError").count(),0);

 await page.goto(url+"/app/settings");
 await page.getByRole("heading",{name:"Settings"}).waitFor();
 await page.getByRole("button",{name:"Sign out"}).click();
 await page.waitForURL(url+"/");
 await page.goto(url+"/app/runs");
 await page.getByRole("button",{name:"demo-python-2026-11-07",exact:true}).waitFor();
 assert.equal(page.url(),url+"/app/runs");
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:"pass",browser:"Firefox",routes:"landing/signup/agents/import/inspect/configure/runs/review/settings",owner:true,download:true,paid_requests:0,seeded_historical_run:seeded.id}));
}finally{
 await browser?.close();
 if(server.exitCode===null){server.kill("SIGTERM");await once(server,"exit");}
}