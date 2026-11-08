import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {readFile, mkdir} from "node:fs/promises";
import {firefox} from "playwright";

const service=spawn("python3",["-m","tests.saas_fixture_server"],{
 stdio:["ignore","pipe","pipe"]});
let origin=null, stderr="", browser;
service.stdout.on("data",chunk=>{
 const match=String(chunk).match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);
 if(match)origin=JSON.parse(match[1]).url;
});
service.stderr.on("data",chunk=>stderr+=String(chunk).slice(-1500));
try{
 for(let i=0;i<120&&!origin;i++)await new Promise(r=>setTimeout(r,100));
 assert.ok(origin,stderr||"No fixture URL");
 browser=await firefox.launch();
 const context=await browser.newContext({
  ignoreHTTPSErrors:true,viewport:{width:390,height:844},
  reducedMotion:"reduce"});
 const page=await context.newPage();
 const errors=[];
 page.on("pageerror",error=>errors.push(error.message));
 await page.goto(origin+"/app/agents/new");
 await page.getByRole("heading",{name:"Bring your agent"}).waitFor();
 await page.locator("#repository").waitFor();
 assert.equal(await page.getByRole("button",{name:/Inspect agent/}).isVisible(),true);
 assert.equal(await page.locator("#zip").count(),1);
 const cookies=await context.cookies();
 const session=cookies.find(cookie=>cookie.name==="__Host-refit-session");
 assert.ok(session?.secure&&session?.httpOnly&&session?.sameSite==="Strict",
   "Guest session must be cookie-secured and no form registration");
 const status=await (await context.request.get(origin+"/api/application/session")).json();
 assert.equal(status.username,"Visitor");
 assert.equal(status.trial,true);
 assert.equal(await page.getByRole("link",{name:/Sign in|Sign up|Create account/}).count(),0);
 const archive=await readFile("data/trial/llm-0.37.1-b9786a2.zip");
 const imported=await context.request.post(origin+"/api/application/imports",{
  headers:{"Origin":origin,"Content-Type":"application/json"},
  data:{method:"zip",archive:archive.toString("base64")},
 });
 assert.equal(imported.status(),201,JSON.stringify(await imported.json()));
 const project=await imported.json();
 assert.equal(project.discovery.preset,"llm-0.37.1");
 await page.goto(origin+"/app/agents");
 const source=page.getByRole("button",{name:/Uploaded ZIP/});
 await source.waitFor();
 await source.click();
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 await page.getByRole("heading",{name:"Configure migration"}).waitFor();
 assert.equal(await page.getByRole("button",{name:/Run migration/}).isVisible(),true);
 assert.ok(!page.url().includes("/login"));
 await mkdir("artifacts/saas-ui",{recursive:true});
 await page.screenshot({path:"artifacts/saas-ui/19-open-import-wizard.png",fullPage:true});
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:"pass",signup_required:false,auto_guest:true,
  actual_zip_import:true,original_agent_discovery:true,configuration_without_auth:true,
  paid_inference:0}));
}finally{await browser?.close();service.kill("SIGKILL");}
