import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.REFIT_BROWSER_URL || "http://127.0.0.1:8097";
await mkdir("artifacts", { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ acceptDownloads: true, viewport: { width: 1280, height: 820 } });
  const pageErrors = [];
  page.on("pageerror", e => pageErrors.push(e.message));
  const response = await page.goto(base + "/", { waitUntil: "domcontentloaded" });
  assert.equal(response?.status(), 200);
  await page.waitForFunction(() => document.querySelector("#recordStatus")?.textContent === "Verified repair");
  assert.match(await page.locator("#recordModels").innerText(), /deepseek-v4.1-flash-1017.*muse-glimmer-30b/i);
  const cards = page.locator(".example");
  assert.equal(await cards.count(), 2);
  const metricText = await page.locator("#metrics").innerText();
  assert.match(metricText, /8\/8/);
  assert.match(metricText, /6\/8/);
  assert.equal(await page.locator("#diagnoseButton").isDisabled(), true);

  await page.locator("#intentText").fill("Move our refund agent from DeepSeek to Muse.");
  await page.locator("#interpretButton").click();
  await page.waitForFunction(() =>
    document.querySelector("#intentResult")?.textContent?.includes("Ready for review:"));
  assert.match(await page.locator("#intentResult").innerText(), /refund/);

  const downloadPromise = page.waitForEvent("download");
  await page.locator("#artifactButton").click();
  const download = await downloadPromise;
  const data = JSON.parse(await readFile(await download.path(), "utf8"));
  assert.equal(data.format, "refit.compatibility.v1");
  assert.equal(data.patch_type, "instructions_only");
  assert.ok(data.target_profile.instructions.includes("get_order"));

  await page.locator('[data-id="recorded-deployment-2026-11-06"]').click();
  await page.waitForFunction(() =>
    document.querySelector("#recordStatus")?.textContent === "Compatible on sample");
  assert.equal(await page.locator("#artifactButton").isVisible(), false);
  const deploymentMetrics = await page.locator("#metrics").innerText();
  assert.match(deploymentMetrics, /8\/8/);

  await page.screenshot({ path: "artifacts/refit-browser-demo.png", fullPage: true });
  assert.deepEqual(pageErrors, [], "Browser runtime errors");
  console.log(JSON.stringify({status:"pass", cases:["real API evidence", "natural language interpretation", "verified artifact export", "no-regression behavior", "no JS exceptions"], screenshot:"artifacts/refit-browser-demo.png"}, null, 2));
} finally {
  await browser.close();
}
