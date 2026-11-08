import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdir} from "node:fs/promises";
import {firefox} from "playwright";

const server=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","pipe"]});
let origin=null, errors="", browser;
server.stdout.on("data",buffer=>{
 const found=String(buffer).match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);
 if(found)origin=JSON.parse(found[1]).url;
});
server.stderr.on("data",buffer=>errors+=String(buffer).slice(-1400));
try {
 for(let i=0;i<100&&!origin;i++)await new Promise(resolve=>setTimeout(resolve,100));
 assert.ok(origin,errors||"Fixture did not launch");
 browser=await firefox.launch();
 const context=await browser.newContext({
  ignoreHTTPSErrors:true, viewport:{width:390,height:844}, reducedMotion:"reduce",
 });
 const page=await context.newPage();
 const clientErrors=[];
 page.on("pageerror",error=>clientErrors.push(error.message));
 await page.goto(origin+"/");
 assert.equal(await page.getByRole("link",{name:/Import your agent/}).count(),1);
 await page.goto(origin+"/app/agents/new");
 await page.getByRole("heading",{name:"Bring your agent"}).waitFor();
 const inspect=page.getByRole("button",{name:/Inspect agent/});
 assert.equal(await inspect.count(),1);
 assert.ok(await page.getByText("GitHub repository").first().isVisible());
 const run=page.getByRole("button",{name:/Run a live sample instead/});
 assert.equal(await run.count(),1);
 await mkdir("artifacts/saas-ui",{recursive:true});
 await page.screenshot({path:"artifacts/saas-ui/17-public-trial-before.png",fullPage:true});
 await run.click();
 await page.waitForURL(/\/app\/runs\/app-[0-9a-f]{16}$/,{timeout:12000});
 await page.getByRole("heading",{name:/simonw\/llm|Migration review/}).first().waitFor();
 const session=await (await context.request.get(origin+"/api/application/session")).json();
 assert.equal(session.trial,true);
 assert.equal(session.username,"Visitor");
 assert.ok(!page.url().includes("/login"),"The visitor must not enter the login flow");
 const cookies=await context.cookies();
 const sessionCookie=cookies.find(cookie=>cookie.name==="__Host-refit-session");
 assert.ok(sessionCookie&&sessionCookie.httpOnly&&sessionCookie.secure);
 const duplicate=await context.request.post(origin+"/api/application/try",{
  headers:{"Origin":origin},
  data:{},
 });
 assert.equal(duplicate.status(),202,"An authenticated visitor may repeat a bounded live sample");
 const additional=await duplicate.json();
 assert.match(additional.id,/^app-[0-9a-f]{16}$/);
 const history=await (await context.request.get(origin+"/api/application/runs")).json();
 assert.ok(history.runs.some(r=>r.id===additional.id),"Repeated sample remains visible to the original guest");
 assert.deepEqual(clientErrors,[]);
 await page.screenshot({path:"artifacts/saas-ui/18-public-trial-after.png",fullPage:true});
 console.log(JSON.stringify({status:"pass",mode:"zero-inference fixture",guest:true,
  requires_signup:false,live_api_route:"/api/application/try",repeat_sample_allowed:true,
  http_only_guest_session:true,owner_scoped_run:true}));
} finally {
 await browser?.close();
 server.kill("SIGKILL");
}
