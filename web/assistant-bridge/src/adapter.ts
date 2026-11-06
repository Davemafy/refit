import type { ChatModelAdapter } from "@assistant-ui/react";
import { RefitApi, type AgentDomain, type RecordedRun, type RunListItem } from "./refit-api";

type Api = Pick<RefitApi, "interpret" | "runs" | "run">;
const viewPattern = /^(?:show|view|open|inspect)\s+(?:the\s+)?(refund|deployment)(?:\s+(?:example|run|migration|agent|evidence))?[.!]?\s*$/i;

function score(entry?: { passed: number; total: number }): string {
  return entry ? entry.passed + "/" + entry.total : "not evaluated";
}
export function formatRecordedEvidence(run: RecordedRun): string {
  const r = run.report;
  const domain = run.domain === "refund" ? "Customer refunds" : "Deployment recovery";
  const lines = [
    domain + " — recorded Vultr inference, synthetic business state",
    "Source: " + run.source + " — " + score(r.source_training),
    "Replacement: " + run.target + " — " + score(r.target_training),
  ];
  if (run.status === "verified_adaptation") {
    if (!r.validation || !r.original_holdout || !r.repaired_holdout) {
      throw new Error("Verified repair is missing independent evidence");
    }
    lines.push(
      "Result: verified adaptation on this sample.",
      "Independent validation: " + score(r.validation),
      "Holdout: " + score(r.original_holdout) + " unmodified → " + score(r.repaired_holdout) + " repaired.",
      "Compatibility artifact: /api/runs/" + run.id + "/artifact",
    );
  } else if (run.status === "compatible_on_sample") {
    lines.push(
      "Result: replacement model compatible on this tested sample.",
      "No repair needed or generated.",
      ...(r.validation ? ["Independent validation: " + score(r.validation)] : []),
    );
  } else {
    lines.push("Result: " + run.status + ". No verified repair can be claimed.");
  }
  const failed = r.target_training?.failed;
  if (failed?.length) lines.push("Unmodified target failed: " + failed.slice(0, 8).join(", "));
  if (run.evidence_url?.startsWith("https://github.com/")) {
    lines.push("Reproducible experiment: " + run.evidence_url);
  }
  lines.push("Scope: built-in agent fixtures only. This does not migrate external agents.");
  return lines.join("\n");
}

function latestText(messages: readonly {
  role: string;
  content: readonly { type: string; text?: string }[];
}[]): string {
  const last = [...messages].reverse().find((message) => message.role === "user");
  return last?.content.filter((part) => part.type === "text")
    .map((part) => part.text || "").join("\n").trim() || "";
}
async function choose(
  api: Api, domain: AgentDomain, source?: string | null,
  target?: string | null, signal?: AbortSignal,
): Promise<RecordedRun | null> {
  const saved = await api.runs(signal);
  const candidate: RunListItem | undefined = saved.find((entry) =>
    entry.mode === "recorded" &&
    entry.domain === domain &&
    (!source || entry.source === source) &&
    (!target || entry.target === target),
  );
  if (!candidate) return null;
  return api.run(candidate.id, signal);
}

export async function answer(
  api: Api, userText: string, signal?: AbortSignal,
): Promise<string> {
  const text = userText.trim();
  if (!text || text.length > 1200) {
    return "Describe a migration in 1–1200 characters.";
  }
  if (/^(?:examples|list examples|show examples|help)[.!]?\s*$/i.test(text)) {
    const saved = await api.runs(signal);
    return [
      "Refit currently offers these evaluated agent migrations:",
      ...saved.map((run) =>
        "• " + (run.domain === "refund" ? "Customer refunds" : "Deployment recovery") +
        ": " + run.source + " → " + run.target + " (" + run.status + ")",
      ),
      "To view evidence, say “show refund example” or “show deployment example.”",
      "Actual live migrations require an authenticated operator; this public bridge cannot start them.",
    ].join("\n");
  }
  const view = viewPattern.exec(text);
  if (view) {
    const run = await choose(api, view[1] as AgentDomain, null, null, signal);
    return run ? formatRecordedEvidence(run) : "No recorded run exists for that workflow.";
  }
  const intent = await api.interpret(text, signal);
  if (!intent.ready_for_review || !intent.domain || !intent.source_model || !intent.target_model) {
    return (
      "I can't reliably identify the complete migration from that message.\n" +
      "Missing or ambiguous: " + intent.missing.join(", ") + ".\n" +
      "Try: “Migrate the refund agent from DeepSeek to Muse.”\n" +
      "Refit does not guess model names or run an unconfirmed migration."
    );
  }
  const run = await choose(
    api, intent.domain, intent.source_model, intent.target_model, signal,
  );
  if (!run) {
    return (
      "Refit understood this request:\n" +
      "Agent: " + intent.domain + "\n" +
      "Source: " + intent.source_model + "\n" +
      "Target: " + intent.target_model + "\n" +
      "No verified recorded evaluation exists for this exact migration.\n" +
      "The public service cannot start paid runs. No result has been fabricated."
    );
  }
  return formatRecordedEvidence(run);
}
export function createRefitAdapter(api: Api = new RefitApi()): ChatModelAdapter {
  return {
    async run({ messages, abortSignal }) {
      const text = latestText(messages);
      try {
        const response = await answer(api, text, abortSignal);
        return { content: [{ type: "text", text: response }] };
      } catch (error) {
        if (abortSignal.aborted) throw error;
        // The official runtime owns error presentation. Never manufacture a
        // fake migration-success response when the backend is unavailable.
        throw new Error(
          error instanceof Error
            ? "Refit backend unavailable or response invalid: " + error.message
            : "Refit backend unavailable",
        );
      }
    },
  };
}
export const refitAdapter = createRefitAdapter();
