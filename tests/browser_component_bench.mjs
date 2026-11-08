import assert from "node:assert/strict";
import {mkdir} from "node:fs/promises";
import {firefox} from "playwright";

const browser=await firefox.launch({headless:true});
const fixture=new URL("./fixtures/workbench-components.html",import.meta.url).href;
const output="artifacts/saas-ui/component-bench";
await mkdir(output,{recursive:true});
const findings=[];
try{
 for(const theme of ["light","dark"]){
  for(const width of [390,768,1024,1440]){
   const page=await browser.newPage({viewport:{width,height:900},reducedMotion:"reduce"});
   const errors=[];
   page.on("pageerror",err=>errors.push(err.message));
   await page.goto(fixture,{waitUntil:"load"});
   await page.getByLabel("Theme").selectOption(theme);
   assert.equal(await page.locator("html").getAttribute("data-theme"),theme);
   assert.equal(await page.getByRole("heading",{name:"Refit / Component bench"}).count(),1);
   assert.equal(await page.locator(".table tbody tr").count(),4);
   const docWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
   assert.equal(docWidth,width,"Component fixture must fit the viewport");
   const button=page.getByRole("button",{name:"Run migration"});
   await button.focus();
   const focus=await button.evaluate(node=>getComputedStyle(node).outlineStyle);
   assert.notEqual(focus,"none","Keyboard focus must be visible");
   assert.equal(await page.getByRole("button",{name:"Unavailable"}).isDisabled(),true);
   assert.deepEqual(errors,[]);
   if(width===390||width===1440)await page.screenshot({path:`${output}/${theme}-${width}.png`,fullPage:true});
   findings.push({theme,width,docWidth,focus,buttons:await page.locator(".preview-row .btn").count()});
   await page.close();
  }
 }
 console.log(JSON.stringify({fixture:"workbench-components",findings},null,2));
} finally{await browser.close();}
