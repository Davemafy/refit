import assert from "node:assert/strict";
import { chromium } from "playwright";

const origin = process.env.REFIT_BRIDGE_URL || "http://127.0.0.1:3007";
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 840 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));

  const response = await page.goto(origin, { waitUntil: "domcontentloaded" });
  assert.equal(response?.status(), 200);
  await page.getByPlaceholder("Describe a migration or request an example…").fill("show refund example");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".message.assistant").last().getByText(/verified adaptation on this sample/i).waitFor();
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
  await page.screenshot({ path: "/tmp/refit-assistant-bridge-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 375, height: 810 });
  await page.screenshot({ path: "/tmp/refit-assistant-bridge-mobile.png", fullPage: true });
  console.log(JSON.stringify({
    status: "pass",
    browser: "Chromium headless",
    cases: ["refund regression", "compatible deployment", "no invented unmatched model", "no browser errors"],
    messages: await page.locator(".message.assistant").count(),
  }, null, 2));
} finally {
  await browser.close();
}
