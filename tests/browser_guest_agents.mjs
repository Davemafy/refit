import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {firefox} from "playwright";
const s=spawn("python3",["-m","tests.saas_fixture_server"],{stdio:["ignore","pipe","ignore"]});
let base;
s.stdout.on("data",b=>{const m=b.toString().match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);if(m)base=JSON.parse(m[1]).url;});
let b;
try{
 for(let i=0;i<120&&!base;i++)await new Promise(r=>setTimeout(r,100));
 assert.ok(base);
 b=await firefox.launch();
 const p=await b.newPage({ignoreHTTPSErrors:true,viewport:{width:360,height:780}});
 await p.addInitScript(()=>localStorage.setItem("refit-theme","dark"));
 await p.emulateMedia({reducedMotion:"reduce"});
 await p.goto(base+"/app/agents");
 await p.getByRole("heading",{name:"Agents"}).waitFor();
 assert.equal(await p.getByText("No agents imported").count(),0);
 assert.equal(await p.locator(".top-context").isVisible(),false,"Avoid repeating the page name in mobile header");
 assert.equal(await p.getByRole("link",{name:"Bring your own agent"}).count(),1);
 assert.equal(await p.getByRole("button",{name:"Recorded Python agent"}).count(),1);
 assert.equal(await p.getByRole("button",{name:/Review run/}).count(),1);
 const style=await p.evaluate(()=>({primary:getComputedStyle(document.querySelector(".page-lead .primary")).backgroundColor,tab:getComputedStyle(document.querySelector(".mobile-nav .selected")).borderBottomColor,icon:getComputedStyle(document.querySelector(".agent-record-icon")).color}));
 assert.equal(style.primary,"rgb(236, 235, 230)");
 assert.equal(style.tab,"rgb(196, 199, 187)");
 await p.screenshot({path:"artifacts/saas-ui/16-guest-agents-neutral.png",fullPage:true});
 console.log(JSON.stringify({status:"pass",import_actions:1,recorded_examples:1,misleading_empty_states:0,style}));
}finally{await b?.close();s.kill("SIGKILL");}