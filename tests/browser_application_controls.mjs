// Isolated gVisor control tests. This fixture never calls the inference broker.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { firefox } from "playwright";

const state = await mkdtemp(join(tmpdir(), "refit-browser-controls-"));
const token = "application-controls-test-operator";
const origin = "http://127.0.0.1:8099";
const zip = execFileSync("python", ["-c", `
import io, sys, zipfile
output=io.BytesIO()
with zipfile.ZipFile(output, "w") as archive:
    archive.writestr(sys.argv[1], sys.argv[2])
sys.stdout.buffer.write(output.getvalue())
`, "agent.py", "import time\ntime.sleep(60)\n"]);
const unsupported = execFileSync("python", ["-c", `
import io, sys, zipfile
output=io.BytesIO()
with zipfile.ZipFile(output, "w") as archive:
    archive.writestr("agent.ts", "export const agent = () => 1")
sys.stdout.buffer.write(output.getvalue())
`]);
const setup = { module: "agent", args: ["{prompt}"], cases:
  ["train", "validation", "holdout"].map(split => ({ name: split, split, prompt: split, stdout: split })) };
let server, browser;

async function launch() {
  server = spawn("python", ["-m", "scripts.application_http", "--state", state,
    "--port", "8099", "--daily-budget", "2"], {
    stdio: ["ignore", "inherit", "inherit"],
    env: { ...process.env, REFIT_APPLICATION_TOKEN: token, VULTR_INFERENCE_API_KEY: "unused-test-placeholder" }
  });
  for (let attempt = 0; attempt < 50; attempt++) {
    if (server.exitCode !== null) throw Error("Control server stopped during launch");
    try { if ((await fetch(origin + "/bring")).ok) return; } catch {}
    await delay(150);
  }
  throw Error("Control server did not start");
}

async function stop() {
  if (server && server.exitCode === null && !server.signalCode) {
    const exited = once(server, "exit");
    server.kill("SIGKILL");
    await exited;
  }
}

try {
  await launch();
  browser = await firefox.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(20_000);
  await page.goto(origin + "/bring");
  await page.getByLabel("Operator access token").fill(token);
  await page.locator("#method").selectOption("zip");

  async function inspect(buffer) {
    await page.locator("#method").selectOption("zip");
    await page.locator("#zip").setInputFiles({ name: "agent.zip", mimeType: "application/zip", buffer });
    const received = page.waitForResponse(r => r.url().endsWith("/api/application/imports"));
    await page.getByRole("button", { name: "Inspect source" }).click();
    assert.equal((await received).status(), 201);
  }

  await inspect(unsupported);
  await page.getByText(/TypeScript execution is unavailable/).waitFor();
  assert.equal(await page.getByRole("button", { name: "Run migration" }).isVisible(), false);

  async function start(expected, budget = 1) {
    await inspect(zip);
    await page.getByRole("button", { name: "Run migration" }).waitFor();
    const setupPanel = page.locator("#setupPanel");
    if (!(await setupPanel.evaluate(el => el.open))) await setupPanel.locator("summary").click();
    await page.getByLabel("Application contract JSON").fill(JSON.stringify(setup));
    await page.getByLabel("Maximum Vultr requests").fill(String(budget));
    await page.getByLabel("I authorize this inference budget.").check();
    const received = page.waitForResponse(r => r.url().endsWith("/api/application/runs"));
    await page.getByRole("button", { name: "Run migration" }).click();
    const response = await received;
    assert.equal(response.status(), expected, await response.text());
    return response.json();
  }

  async function assertSafe(id, status) {
    const headers = { Authorization: "Bearer " + token };
    const base = origin + "/api/application/runs/" + id;
    const response = await page.request.get(base + "/evidence", { headers });
    const proof = await response.json();
    assert.equal(proof.run.status, status);
    assert.equal(proof.run.model_requests, 0);
    assert.equal(proof.run.export, null);
    assert.equal(proof.events.filter(e => e.type === "inference_requested").length, 0);
    assert.ok(proof.events.some(e => e.type === "sandbox_cleanup" && e.details.receipt.verified));
    assert.equal((await page.request.get(base + "/artifact", { headers })).status(), 409);
  }

  const cancelled = await start(202);
  await page.locator("#sandbox").filter({ hasText: "gVisor container running" }).waitFor();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.locator("#outcome").filter({ hasText: "Cancelled" }).waitFor();
  await assertSafe(cancelled.id, "cancelled");

  const interrupted = await start(202);
  await page.locator("#sandbox").filter({ hasText: "gVisor container running" }).waitFor();
  await stop();
  await launch();
  await page.reload();
  await page.getByLabel("Operator access token").fill(token);
  assert.equal(await page.getByLabel("Run ID").inputValue(), interrupted.id);
  await page.getByRole("button", { name: "Open run" }).click();
  await page.locator("#outcome").filter({ hasText: "Interrupted" }).waitFor();
  await assertSafe(interrupted.id, "interrupted");
  const quota = await start(429, 2);
  assert.equal(quota.error.code, "daily_budget_exhausted");
  await page.getByRole("alert").getByText("This operator's daily request allowance is reserved.").waitFor();
  console.log(JSON.stringify({ unsupported: true, cancelled: cancelled.id, interrupted: interrupted.id,
    quota: quota.error.code, inferenceRequests: 0 }));
} finally {
  await browser?.close();
  await stop();
  await rm(state, { recursive: true, force: true });
}
