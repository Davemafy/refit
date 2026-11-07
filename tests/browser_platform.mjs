// Real HTTPS acceptance. The only paid operation is an explicit --execute.
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { firefox } from "playwright";

const origin = process.env.REFIT_PLATFORM_URL || "https://80.240.30.92";
const archive = process.env.REFIT_PLATFORM_ARCHIVE;
const setupFile = process.env.REFIT_PLATFORM_SETUP;
const output = process.env.REFIT_PLATFORM_OUTPUT || "artifacts/platform-browser";
const paid = process.argv.includes("--execute");
const path = "/api/application";
const runtime = process.env.REFIT_PLATFORM_RUNTIME || "typescript";
const cap = runtime === "python" ? 8 : 16;
assert(new URL(origin).protocol === "https:");
assert(archive && setupFile);
await mkdir(output, { recursive: true });
const browser = await firefox.launch();
const errors = [];
const { model: source, replacement: target } = {
  model: "deepseek-v4.1-flash-1017", replacement: "glm-5.2"
};

try {
  const credentials = [];
  const pages = [];
  for (const index of [0, 1]) {
    const context = await browser.newContext({ viewport: { width: 1150, height: 900 }, acceptDownloads: true });
    const page = await context.newPage();
    page.setDefaultTimeout(25_000);
    page.on("pageerror", error => errors.push(error.message));
    const status = await page.goto(origin + "/signup");
    assert.equal(status.status(), 200);
    await page.getByRole("heading", { name: "Create your account" }).waitFor();
    const user = { username: `judge-${index}-${randomBytes(5).toString("hex")}`,
      password: randomBytes(24).toString("base64url") };
    credentials.push(user);
    await page.locator("#username").fill(user.username);
    await page.locator("#password").fill(user.password);
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.waitForURL(origin + "/app");
    await page.goto(origin + "/app/agents/new");
    await page.getByRole("heading", { name: "Bring your agent" }).waitFor();
    const cookie = (await context.cookies()).find(c => c.name === "__Host-refit-session");
    assert.ok(cookie?.httpOnly && cookie?.secure && cookie?.sameSite === "Strict");
    pages.push(page);
  }
  const [owner, other] = pages;
  await owner.getByRole("button", { name: "Upload ZIP" }).click();
  await owner.locator("#zip").setInputFiles(archive);
  const importing = owner.waitForResponse(r => r.url().endsWith(path + "/imports"));
  await owner.getByRole("button", { name: /Inspect agent/ }).click();
  const imported = await (await importing).json();
  assert.equal(imported.discovery.runtime, runtime);
  if (runtime === "typescript") await owner.getByText(/Vercel AI SDK/).waitFor();
  else await owner.getByText(/python -m src.qa/).waitFor();
  const setup = JSON.parse(await readFile(setupFile, "utf8"));

  async function request(page, suffix, data) {
    return page.evaluate(async ({ url, data }) => {
      const r = await fetch(url, data === undefined ? {} : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
      });
      return { status: r.status, body: await r.json() };
    }, { url: path + suffix, data });
  }

  assert.equal((await request(other, "/projects")).body.projects.length, 0);
  const runInput = { import_id: imported.id, source, target, budget: cap, authorize: true, setup };
  assert.equal((await request(other, "/runs", runInput)).status, 404);
  assert.equal((await request(other, "/projects/" + imported.id + "/remove", {})).status, 404);
  let live = null;
  if (paid) {
    await owner.getByRole("button", { name: /Continue to configuration/ }).click();
    await owner.locator("#source").selectOption(source);
    await owner.locator("#target").selectOption(target);
    await owner.getByRole("button", { name: "Edit JSON" }).click();
    await owner.locator("#setup").fill(JSON.stringify(setup));
    await owner.locator("#budget").fill(String(cap));
    await owner.locator("#authorize").check();
    const starting = owner.waitForResponse(r => r.url().endsWith(path + "/runs") && r.request().method() === "POST");
    await owner.getByRole("button", { name: /Run migration/ }).click();
    const response = await starting;
    assert.equal(response.status(), 202, await response.text());
    const accepted = await response.json();
    console.log(JSON.stringify({ accepted: accepted.id, cap: accepted.budget }));
    const runRoute = "/runs/" + accepted.id;
    assert.equal((await request(other, runRoute)).status, 404);
    assert.equal((await request(other, runRoute + "/events")).status, 404);
    assert.equal((await request(other, runRoute + "/evidence")).status, 404);
    assert.equal((await request(other, runRoute + "/artifact")).status, 404);
    assert.equal((await request(other, runRoute + "/cancel", {})).status, 404);

    await owner.waitForURL(origin + "/app/runs/" + accepted.id);
    // Poll the persisted owner-scoped status, not a presentation-only label.
    let completed;
    for (let attempt = 0; attempt < 100; attempt++) {
      completed = await request(owner, runRoute);
      if (completed.status === 200 && !["running", "cancelling"].includes(completed.body.status)) break;
      await new Promise(resolve => setTimeout(resolve, 1700));
    }
    assert.equal(completed.status, 200);
    assert.ok(!["running", "cancelling"].includes(completed.body.status), "Migration did not reach a terminal status.");
    await owner.goto(origin + "/app/runs/" + accepted.id);

    async function download(name, suffix) {
      const pending = owner.waitForEvent("download");
      await owner.getByRole("button", { name }).click();
      const file = await pending;
      const body = await readFile(await file.path());
      await writeFile(`${output}/${accepted.id}-${suffix}.json`, body);
      return JSON.parse(body);
    }

    const evidence = await download("Download evidence", "evidence");
    live = { id: accepted.id, status: evidence.run.status, requests: evidence.run.model_requests };
    console.log(JSON.stringify(live));
    assert.equal(evidence.run.status, "compatible_on_sample");
    assert.ok(evidence.run.model_requests <= cap);
    assert.equal(evidence.run.configuration_sha256.length, 71);
    const receipts = evidence.events.filter(e => e.type === "sandbox_cleanup");
    assert.equal(receipts.length, 7);
    assert.ok(receipts.every(e => e.details.receipt.verified));
    const cases = evidence.events.filter(e => e.type === "case_completed");
    assert.equal(cases.length, 7);
    if (runtime === "typescript") assert.ok(cases.every(e => e.details.verdict.required_tool_observed));
    const config = await download("Export verified configuration", "artifact");
    assert.deepEqual(config, evidence.run.export);
    if (runtime === "typescript") assert.equal(config.entry, "invoke.ts");
    else assert.equal(config.module, "src.qa");
    assert.equal(config.environment.OPENAI_MODEL, target);
    await owner.screenshot({ path: `${output}/${accepted.id}.jpg`, type: "jpeg", quality: 62, fullPage: true });
    await owner.goto(origin + "/app/runs");
    await owner.getByRole("button", { name: accepted.id, exact: true }).click();
    await owner.getByRole("button", { name: /Export verified configuration/ }).first().waitFor();
  }
  await other.goto(origin + "/app/settings");
  await other.getByRole("button", { name: "Sign out" }).click();
  await other.waitForURL(origin + "/");
  assert.equal((await request(other, "/projects")).status, 401);
  await other.goto(origin + "/login");
  await other.locator("#username").fill(credentials[1].username);
  await other.locator("#password").fill(credentials[1].password);
  await other.getByRole("button", { name: /Continue/ }).click();
  await other.waitForURL(origin + "/app");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ browser: "Firefox", twoAccounts: true, isolation: true, live }));
} finally {
  await browser.close();
}
