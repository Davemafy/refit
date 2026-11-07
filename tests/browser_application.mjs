// Exercise the operator UI against its real API. A paid start is opt-in.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { firefox } from "playwright";

const origin = process.env.REFIT_APPLICATION_URL || "http://127.0.0.1:8098";
const token = process.env.REFIT_APPLICATION_TOKEN;
const oldRun = process.env.REFIT_BROWSER_REOPEN || "app-3df57a3a263249eb";
const revision = "b9786a2daa44a995ff7719c655c5338bf685d551";
const source = "deepseek-v4.1-flash-1017";
const target = "glm-5.2";
const generic = process.argv.includes("--execute-generic");
const startLive = generic || process.argv.includes("--execute");
const cap = generic ? 8 : 16;
const genericArchive = process.env.REFIT_GENERIC_ZIP;
const genericSetup = {
  module: "src.qa", args: ["{prompt}"],
  cases: [
    { name: "gauss", split: "train",
      prompt: "请从知识库逐字复制高斯定律的积分公式（不要添加 Markdown 或解释）。第一行只写公式，第二行只写来源页标题，格式 [[页面标题]]。",
      stdout: "∮ E · dS = Q_enc / epsilon_0\n[[高斯定律与电通量]]" },
    { name: "magnetic-divergence", split: "validation",
      prompt: "请从麦克斯韦方程组页面逐字复制磁场无源的公式，不改记号。第一行只写原文公式，第二行只写来源页标题，格式 [[页面标题]]。不要添加其他内容。",
      stdout: "nabla · B = 0\n[[麦克斯韦方程组与统一图景]]" },
    { name: "line-current", split: "holdout",
      prompt: "请逐字复制知识库中传输线电流 I 沿 x 变化的偏微分方程。第一行只写原文公式，第二行只写来源页标题，格式 [[页面标题]]。不要使用 LaTeX 或添加解释。",
      stdout: "partial I / partial x = -G V - C partial V / partial t\n[[传输线、驻波与波导]]" }
  ]
};
const output = process.env.REFIT_BROWSER_OUTPUT || "artifacts/application-browser";
assert(token, "Set the operator token in the environment");
await mkdir(output, { recursive: true });
const browser = await firefox.launch();
let page;
try {
  page = await browser.newPage({ viewport: { width: 1160, height: 900 }, acceptDownloads: true });
  page.setDefaultTimeout(20_000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(origin + "/bring");
  await page.getByLabel("Operator access token").fill("wrong-operator-token");
  await page.getByRole("button", { name: "Inspect source" }).click();
  await page.getByRole("alert").getByText("Provide the operator access token.").waitFor();

  await page.getByLabel("Operator access token").fill(token);
  await page.getByLabel("Repository", { exact: true }).fill("simonw/llm");
  await page.getByLabel("Commit SHA").fill(revision);
  await page.getByRole("button", { name: "Inspect source" }).click();
  await page.getByText(/python -m llm/).waitFor();
  await page.getByLabel("Source model").selectOption(source);
  await page.getByLabel("Replacement model").selectOption(target);
  await page.getByLabel("Maximum Vultr requests").fill(String(cap));
  const start = page.getByRole("button", { name: "Run migration" });
  let starts = 0;
  page.on("request", request => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/application/runs") starts++;
  });
  await start.click();
  assert.equal(starts, 0, "The authorization control must prevent an unapproved start");

  async function open(id) {
    const input = page.getByLabel("Run ID");
    const panel = page.locator("details").filter({ has: page.getByText("Open an existing run", { exact: true }) });
    if (!(await panel.evaluate(el => el.open))) await panel.locator("summary").click();
    await input.fill(id);
    await page.getByRole("button", { name: "Open run" }).click();
  }

  async function download(button, id, kind) {
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name: button }).click();
    const file = await pending;
    assert.equal(file.suggestedFilename(), `${id}-${kind}.json`);
    const contents = await readFile(await file.path());
    await writeFile(`${output}/${id}-${kind}.json`, contents);
    return JSON.parse(contents);
  }

  async function verify(id, expectedRevision = revision) {
    await page.waitForFunction(() => {
      const outcome = document.querySelector("#outcome").textContent;
      return !["Opening run", "Migration", "running", "cancelling"].includes(outcome);
    }, null, { timeout: 120_000 });
    const proof = await download("Download evidence", id, "evidence");
    assert.equal(proof.run.status, "compatible_on_sample");
    await page.getByText(/Fresh verification 1\/1/).waitFor();
    await page.getByText("gVisor container removed and verified").waitFor();
    const config = await download("Download verified configuration", id, "artifact");
    assert.equal(proof.run.id, id);
    assert.equal(proof.run.source, source);
    assert.equal(proof.run.target, target);
    assert.deepEqual(config, proof.run.export);
    assert.equal(config.revision, expectedRevision);
    assert.equal(config.model, target);
    assert.ok(proof.run.verification[0].passed);
    const cleanups = proof.events.filter(e => e.type === "sandbox_cleanup");
    assert.equal(cleanups.length, 7);
    assert.ok(cleanups.every(e => e.details.receipt.verified));
    await page.screenshot({ path: `${output}/${id}.png`, fullPage: true,
      mask: [page.getByLabel("Operator access token"), page.getByLabel("Repository read token, for private source")] });
    return proof;
  }

  await open(oldRun);
  await verify(oldRun);
  let live = null;
  if (startLive) {
    if (generic) {
      assert(genericArchive, "Set REFIT_GENERIC_ZIP to the pinned QA runtime snapshot");
      await page.getByLabel("Source", { exact: true }).selectOption("zip");
      await page.getByLabel(/Project ZIP/).setInputFiles(genericArchive);
      await page.getByRole("button", { name: "Inspect source" }).click();
      await page.getByText(/Provide a Python module/).waitFor();
      await page.getByText("Python entry and verification cases").click();
      await page.getByLabel("Application contract JSON").fill(JSON.stringify(genericSetup));
      await page.getByLabel("Maximum Vultr requests").fill(String(cap));
    }
    await page.getByLabel("I authorize this inference budget.").check();
    const pending = page.waitForResponse(response =>
      response.request().method() === "POST" && new URL(response.url()).pathname === "/api/application/runs");
    const streaming = page.waitForResponse(response => /\/runs\/app-[0-9a-f]{16}\/events\?/.test(response.url()));
    await start.click();
    const response = await pending;
    assert.equal(response.status(), 202, await response.text());
    const accepted = await response.json();
    assert.equal(accepted.budget, cap);
    assert.equal(accepted.status, "running");
    assert.equal(starts, 1);
    console.log(JSON.stringify({ accepted: accepted.id, authorizedRequests: accepted.budget }));
    assert.equal((await streaming).status(), 200);
    const proof = await verify(accepted.id, generic ? null : revision);
    assert.ok(proof.run.model_requests > 0 && proof.run.model_requests <= cap);
    if (generic) {
      assert.equal(proof.run.import.discovery.preset, null);
      assert.equal(proof.run.export.seam, "openai-env");
      assert.equal(proof.run.export.environment.OPENAI_MODEL, target);
    } else {
      assert.ok(proof.events.some(e => e.type === "inference_completed" && e.details.tools_called?.includes("llm_version")));
    }
    live = { id: accepted.id, requests: proof.run.model_requests,
      importSeconds: proof.run.import.import_seconds, executionSeconds: proof.run.execution_seconds };
    await page.reload();
    await page.getByLabel("Operator access token").fill(token);
    assert.equal(await page.getByLabel("Run ID").inputValue(), accepted.id);
    await open(accepted.id);
    await page.locator("#outcome").filter({ hasText: "Compatible on evaluated cases" }).waitFor();
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ browser: "Firefox", reopened: oldRun, live, requestsStarted: starts }));
} catch (error) {
  if(page) console.error(JSON.stringify({ outcome: await page.locator("#outcome").textContent(),
    issue: await page.locator("#error").textContent(), summary: await page.locator("#summary").textContent() }));
  throw error;
} finally {
  await browser.close();
}
