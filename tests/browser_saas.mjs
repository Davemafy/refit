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
 await page.getByRole("button",{name:/Inspect published example/}).click();
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 await page.getByText("python -m src.qa").waitFor();
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 await page.getByRole("heading",{name:"Configure migration"}).waitFor();
 await page.getByRole("button",{name:/View recorded results/}).click();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 await page.goto(url+"/app/runs");
 await page.getByRole("button",{name:"demo-python-2026-11-07",exact:true}).waitFor();
 await page.getByRole("button",{name:"demo-python-2026-11-07",exact:true}).click();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
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
 await page.locator("#method").selectOption("zip");
 await page.locator("#zip").setInputFiles({name:"agent.zip",mimeType:"application/zip",buffer:zip});
 await page.getByRole("button",{name:/Inspect source/}).click();
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 await page.getByText("python -m agent").waitFor();
 await page.screenshot({path:"artifacts/saas-ui/02-inspection.png",fullPage:true});
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 await page.getByRole("heading",{name:"Configure migration"}).waitFor();
 assert.deepEqual(await page.locator("#source option").allTextContents(),
  ["deepseek-v4.1-flash-1017","glm-5.2"]);
 await page.locator("#setup").fill(JSON.stringify({module:"agent",args:["{prompt}"],cases:[
  {name:"a",split:"train",prompt:"A",stdout:"ok"},
  {name:"b",split:"validation",prompt:"B",stdout:"ok"},
  {name:"c",split:"holdout",prompt:"C",stdout:"ok"}
 ]}));
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
 await page.getByText(/Sandbox cleanup receipts/).waitFor();
 await page.screenshot({path:"artifacts/saas-ui/04-review.png",fullPage:true});
 await page.getByRole("button",{name:"Trace",exact:true}).click();
 await page.locator(".log").waitFor();
 await page.getByRole("button",{name:"Evidence",exact:true}).last().click();
 await page.getByText(/recorded containers verified cleaned up/).waitFor();

 const waiting=page.waitForEvent("download");
 await page.getByRole("button",{name:/Export verified configuration/}).first().click();
 const downloaded=await waiting;
 assert.ok(downloaded.suggestedFilename().endsWith("-artifact.json"));
 assert.equal(runRequests.length,0,"Fixture UI test must never launch inference");

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