// Read-only Firefox acceptance against the published, recorded migration.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdir} from "node:fs/promises";
import {firefox} from "playwright";

const production = process.env.REFIT_WORKBENCH_URL;
const output = process.env.REFIT_WORKBENCH_OUTPUT || "artifacts/saas-ui/workbench";
const server = production ? null : spawn("python3", ["-m", "tests.saas_fixture_server"], {stdio:["ignore","pipe","inherit"]});
let origin = production;
server?.stdout.on("data", chunk => {
 const match = String(chunk).match(/REFIT_FIXTURE_READY=(\{[^\n]+\})/);
 if (match) origin = JSON.parse(match[1]).url;
});
const paths = [["overview","/app"],["agents","/app/agents"],["runs","/app/runs"],
 ["evidence","/app/evidence"],["settings","/app/settings"],["import","/app/agents/new"]];
let browser;
try {
 for (let i=0; i<100 && !origin; i++) await new Promise(resolve=>setTimeout(resolve,100));
 assert.ok(origin, "Fixture failed to start");
 const widths = [390,768,1024,1366,1440];
 const errors = [];
 await mkdir(output, {recursive:true});
 browser = await firefox.launch();
 const page = await browser.newPage({ignoreHTTPSErrors:!production, viewport:{width:1366,height:768}, acceptDownloads:true, reducedMotion:"reduce"});
 page.on("pageerror", error=>errors.push(error.message));
 await page.goto(origin+"/app");
 await page.getByRole("button",{name:"Try a migration"}).waitFor();
 assert.equal(await page.locator(".topbar").evaluate(e=>e.getBoundingClientRect().height),48);
 assert.equal(await page.locator(".sidebar").evaluate(e=>e.getBoundingClientRect().width),220);
 async function theme(value) {
  await page.locator("summary[aria-label='Workspace preferences']").click();
  await page.getByLabel("Appearance").selectOption(value);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("html").getAttribute("data-theme"),value);
 }
 async function assertFits(width) {
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
 }
 for (const mode of ["dark","light"]) {
  await theme(mode);
  await page.goto(origin+"/app");
  const action=page.getByRole("button",{name:"Try a migration"});
  await action.waitFor();
  const ratios=await action.evaluate(button=>{
   const value=color=>color.match(/[0-9.]+/g).slice(0,3).map(Number).map(n=>{
    const channel=n/255;
    return channel<=0.04045?channel/12.92:((channel+0.055)/1.055)**2.4;
   }).reduce((sum,n,i)=>sum+n*[0.2126,0.7152,0.0722][i],0);
   const contrast=(a,b)=>(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
   const buttonStyle=getComputedStyle(button), pageStyle=getComputedStyle(document.querySelector(".content"));
   return [contrast(value(buttonStyle.color),value(buttonStyle.backgroundColor)),
    contrast(value(pageStyle.color),value(pageStyle.backgroundColor))];
  });
  assert.ok(ratios.every(ratio=>ratio>=4.5),"Primary action and workspace body text must pass 4.5:1");
  for (const [name,path] of paths) {
   await page.goto(origin+path);
   await page.getByRole("heading",{level:1}).waitFor();
   assert.equal(await page.locator("html").getAttribute("data-theme"),mode);
   await page.screenshot({path:output+"/"+mode+"-"+name+".jpg",type:"jpeg",quality:66});
  }
  await page.goto(origin+"/app");
  await page.getByRole("button",{name:"Try a migration"}).click();
  await page.getByRole("heading",{name:"Review migration results"}).waitFor();
  assert.ok(await page.getByRole("button",{name:"Export verified configuration"}).isVisible());
  await page.screenshot({path:output+"/"+mode+"-comparison.jpg",type:"jpeg",quality:66});
  await page.getByRole("button",{name:"Trace",exact:true}).click();
  await page.locator(".trace-branch").first().waitFor();
  assert.ok(await page.locator(".trace-branch .trace-branch").count()>0);
  const branch=page.locator(".trace-branch").first();
  await branch.locator(":scope > summary").click();
  assert.equal(await branch.getAttribute("open"),null);
  await branch.locator(":scope > summary").click();
  const first=page.locator(".trace-entry").first();
  await first.focus();
  await first.press("ArrowDown");
  const current=page.locator(".trace-entry:focus");
  await current.press("Enter");
  const chosen=await page.locator(".trace-entry[aria-pressed=true]").getAttribute("data-seq");
  await page.reload();
  await page.locator(".trace-entry[aria-pressed=true]").waitFor();
  assert.equal(await page.locator(".trace-entry[aria-pressed=true]").getAttribute("data-seq"),chosen);
  await page.screenshot({path:output+"/"+mode+"-trace.jpg",type:"jpeg",quality:66});
 }
 await page.goto(origin+"/app/runs");
 await page.getByRole("heading",{name:"Runs",exact:true}).waitFor();
 await page.keyboard.press("Control+k");
 const palette=page.getByRole("dialog",{name:"Search agents and runs"});
 await palette.waitFor();
 const input=page.getByRole("combobox");
 await input.fill("settings");
 assert.equal(await palette.locator("mark").innerText(),"Settings");
 await input.press("ArrowDown");
 await input.press("Enter");
 await page.waitForURL(origin+"/app/settings");
 await page.locator("#search").click();
 await input.fill("there is no matching run");
 await palette.getByText(/No matches/).waitFor();
 await input.press("Escape");
 await palette.waitFor({state:"hidden"});
 await page.waitForFunction(()=>document.activeElement===document.getElementById("search"));
 await page.locator("#search").click();
 await page.screenshot({path:output+"/command-palette.jpg",type:"jpeg",quality:66});
 await page.keyboard.press("Escape");
 for (const width of widths) {
  await page.setViewportSize({width,height:844});
  for (const [,path] of [...paths,["trace","/app/runs/demo-python-2026-11-07?view=traces"],
   ["comparison","/app/runs/demo-python-2026-11-07"]]) {
   await page.goto(origin+path);
   await page.getByRole("heading",{level:1}).waitFor();
   await assertFits(width);
  }
 }
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:output+"/mobile-comparison.jpg",type:"jpeg",quality:66});
 await page.getByRole("button",{name:"Trace",exact:true}).click();
 await page.locator(".trace-branch").first().waitFor();
 await page.screenshot({path:output+"/mobile-trace.jpg",type:"jpeg",quality:66});
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({origin,widths,themes:["dark","light"],keyboard:true,traceDeepLink:true,paidRequests:0}));
} finally {
 await browser?.close();
 server?.kill();
}
