import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const origin = process.env.REFIT_BRIDGE_URL || "http://127.0.0.1:3007";
const browser = await chromium.launch({ headless: true });
await mkdir("artifacts", { recursive: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 840 } });
  const errors = [];
  const apiCalls = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiCalls.push(request.method() + " " + request.url());
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/")) apiCalls.push("response HTTP " + response.status());
  });

  const response = await page.goto(origin, { waitUntil: "domcontentloaded" });
  assert.equal(response?.status(), 200);
  await page.getByPlaceholder("Describe a migration or request an example…").fill("show refund example");
  await page.getByRole("button", { name: "Send" }).click();
  try {
    await page.locator(".message.assistant").last().getByText(/verified adaptation on this sample/i).waitFor({ timeout: 12000 });
  } catch (error) {
    console.log("MESSAGE DIAGNOSTICS", JSON.stringify(await page.locator(".message").allTextContents()));
    console.log("API TRAFFIC", JSON.stringify(apiCalls));
    console.log("BROWSER ERRORS", JSON.stringify(errors));
    console.log("HTML", (await page.locator("body").innerText()).slice(0, 6000));
    await page.screenshot({ path: "artifacts/refit-assistant-bridge-debug.png", fullPage: true });
    throw error;
  }
  const refund = await page.locator(".message.assistant").last().innerText();
  assert.match(refund, /6\/8/);
  assert.match(refund, /7\/8 unmodified → 8\/8 repaired/);

  await page.getByPlaceholder("Describe a migration or request an example…").fill("show deployment example");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".message.assistant").last().getByText(/No repair needed or generated/i).waitFor();
  const compatible = await page.locator(".message.assistant").last().innerText();
  assert.doesNotMatch(compatible, /Compatibility artifact/);

  await page.getByPlaceholder("Describe a migration or request an example…").fill("Migrate the refund agent from DeepSeek to Raon");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".message.assistant").last().getByText(/No verified recorded evaluation exists/i).waitFor();

  assert.deepEqual(errors, []);
  await page.screenshot({ path: "artifacts/refit-assistant-bridge-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 375, height: 810 });
  await page.screenshot({ path: "artifacts/refit-assistant-bridge-mobile.png", fullPage: true });
  console.log(JSON.stringify({
    status: "pass",
    browser: "Chromium headless",
    cases: ["refund regression", "compatible deployment", "no invented unmatched model", "no browser errors"],
    messages: await page.locator(".message.assistant").count(),
  }, null, 2));
} finally {
  await browser.close();
}
