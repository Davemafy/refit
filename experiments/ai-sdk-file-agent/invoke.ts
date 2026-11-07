// Only the invocation and offline state seam. The agent loop, prompts,
// tool definitions and approvals below are the upstream application's.
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { createAgent, runWithApproval } from "./src/agent/agent-aisdk.ts";
import { resolveInside } from "./src/agent/tools.ts";

const root = resolve("records");
const model = createOpenAICompatible({
  name: "evaluation", baseURL: process.env.OPENAI_BASE_URL!,
  apiKey: process.env.OPENAI_API_KEY!,
  supportsStructuredOutputs: true,
})(process.env.OPENAI_MODEL!);
const agent = createAgent(model, {
  list: path => readdir(resolveInside(root, path)),
  read: path => readFile(resolveInside(root, path), "utf8"),
  write: async () => { throw new Error("The evaluation records are read-only"); }
});
const { final } = await runWithApproval(agent, process.argv[2], async () => false);
if (final.output.written.length !== 0) throw new Error("Unexpected write report");
console.log(final.output.summary);
