// Paid production Firefox acceptance. Uses one scoped reservation of up to 16 requests.
import {firefox} from "playwright";
import assert from "node:assert/strict";
import {readFile,writeFile,mkdir} from "node:fs/promises";
const host=process.env.REFIT_PLATFORM_URL||"https://80.240.30.92";
const out=process.env.REFIT_PLATFORM_OUTPUT||"artifacts/generic-provider";
assert.ok(process.env.REFIT_REVIEW_TOKEN,"Set an unused, scoped review pass for this paid test.");
const browser=await firefox.launch();
const repository="https://github.com/MochiaoChen/mini-agent",revision="e84a70e7d07b617c927c742ffdae15b1a1332a2f";
await mkdir(out,{recursive:true});
try{
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:false,hasTouch:true,acceptDownloads:true});
 const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));page.setDefaultTimeout(25000);
 const grant=page.waitForResponse(r=>r.url().endsWith("/review-session"));
 await page.goto(host+"/app#review="+process.env.REFIT_REVIEW_TOKEN);
 assert.equal((await grant).status(),200);
 await page.getByRole("heading",{name:"Your workspace"}).waitFor();
 await page.goto(host+"/app/agents/new");
 await page.getByLabel("Repository URL").fill(repository);
 await page.locator("#advancedImport summary").click();
 await page.locator("#revision").fill(revision);
 const pending=page.waitForResponse(r=>r.url().endsWith("/api/application/imports")&&r.request().method()==="POST");
 await page.getByRole("button",{name:/Inspect agent/}).click();
 const imported=await pending;
 assert.equal(imported.status(),201,await imported.text());
 const project=await imported.json();
 assert.equal(project.revision,revision);
 await page.getByRole("heading",{name:"Inspect your agent"}).waitFor();
 const candidate=project.discovery.applications.findIndex(a=>a.entry==="python -m mini_agent");
 assert(candidate>=0);
 await page.getByLabel("Application boundary").selectOption(String(candidate));
 await page.getByRole("button",{name:/Continue to configuration/}).click();
 const provider=page.getByLabel("Provider environment variables");
 await provider.selectOption("generic");
 assert.equal(await page.locator("#entryPoint").inputValue(),"mini_agent");
 await page.locator("#runtimeArgs").fill("--yolo\n{prompt}");
 await page.locator("#source").selectOption("glm-5.2");
 await page.locator("#target").selectOption("deepseek-v4.1-flash-1017");
 for (const [i,[name,state]] of [["invoice","reviewed"],["shipment","ready"],["receipt","confirmed"]].entries()){
  const group=page.locator(".setup-case").nth(i),file=name+".json";
  if(await group.getAttribute("open")===null)await group.locator(":scope > summary").click();
  await group.locator('[data-case="name"]').fill(name);
  await group.locator('[data-case="prompt"]').fill('Call write_file once. For the path argument use the literal string '+JSON.stringify(file)+' with no directory or ./ prefix. For the content argument write exactly this JSON object: '+JSON.stringify({status:state})+'. Do not use bash or change any other files. After the tool completes, respond DONE.');
  await group.getByText("Structured output and tools",{exact:true}).click();
  await group.locator('[data-case="tool"]').fill("write_file");
  await group.locator('[data-case="tool_arguments"]').fill(JSON.stringify({path:file}));
  await group.locator('[data-case="forbidden_tools"]').fill("bash");
  await group.getByText("Application state checks",{exact:true}).click();
  await group.locator('[data-case="state"]').fill(JSON.stringify([{path:file,op:"changed"},{path:file,op:"json_contains",expected:{status:state}},{path:"mini_agent.py",op:"unchanged"}]));
 }
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
 await page.screenshot({path:out+"/mobile-config.jpg",type:"jpeg",quality:63});
 await page.locator("#budget").fill("16");
 await page.locator("#authorize").check();
 const acceptance=page.waitForResponse(r=>r.url().endsWith("/api/application/runs")&&r.request().method()==="POST");
 await page.getByRole("button",{name:"Run migration"}).click();
 const response=await acceptance;
 assert.equal(response.status(),202,await response.text());
 const run=await response.json();
 console.log(JSON.stringify({id:run.id,project:project.id,revision,importSeconds:project.import_seconds,cap:run.budget}));
 await page.waitForURL(host+"/app/runs/"+run.id);
 let finished;
 for(let i=0;i<100;i++){
  const read=await page.request.get(host+"/api/application/runs/"+run.id);
  if(read.ok())finished=await read.json();
  if(finished&&!["queued","running","cancelling"].includes(finished.status))break;
  await new Promise(r=>setTimeout(r,1300));
 }
 await page.reload();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 async function download(label,suffix){
  const pending=page.waitForEvent("download");
  await page.getByRole("button",{name:label,exact:true}).click();
  const body=await readFile(await (await pending).path());
  await writeFile(out+"/"+run.id+"-"+suffix+".json",body);
  return JSON.parse(body);
 }
 const report=await download("Download evidence","evidence");
 const rows=report.events.filter(e=>e.type==="case_completed").map(e=>({phase:e.details.phase,passed:e.details.passed,error:e.details.error,tools:e.details.trace?.flatMap(t=>t.tools_called||[]),state:e.details.state_checks?.map(c=>c.passed)}));
 const receipts=report.events.filter(e=>e.type==="sandbox_cleanup").map(e=>e.details.receipt.verified);
 console.log(JSON.stringify({status:report.run.status,error:report.run.error,requests:report.run.model_requests,seconds:report.run.execution_seconds,receipts,rows}));
 await page.screenshot({path:out+"/mobile-result.jpg",type:"jpeg",quality:66});
 assert.equal(report.run.status,"compatible_on_sample");
 assert.equal(receipts.length,7);
 assert.ok(receipts.every(Boolean));
 assert.ok(rows.every(r=>r.passed&&r.state.every(Boolean)&&r.tools.includes("write_file")));
 const exported=await download("Export verified configuration","export");
 assert.deepEqual(exported,report.run.export);
 assert.equal(exported.module,"mini_agent");
 assert.equal(exported.provider_env,"generic");
 assert.equal(exported.environment.MODEL,"deepseek-v4.1-flash-1017");
 assert.equal(exported.credential_env,"API_KEY");
 assert.equal(exported.revision,revision);
 assert.ok(report.run.verification.every(v=>v.passed));
 assert.deepEqual(errors,[]);
 await page.setViewportSize({width:1280,height:900});
 await page.reload();
 await page.getByRole("heading",{name:"Review migration results"}).waitFor();
 await page.screenshot({path:out+"/desktop-result.jpg",type:"jpeg",quality:66});
} catch(e){ console.error(String(e).replace(/review=[a-zA-Z0-9_-]{43}/g,"review=REDACTED"));process.exitCode=1; }
finally{await browser.close();}
