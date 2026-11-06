import { describe, expect, it, vi } from "vitest";
import { RefitApi, assertRun, type RecordedRun, type RefitIntent } from "../src/refit-api";
import { answer, formatRecordedEvidence } from "../src/adapter";

const refund: RecordedRun = {
  id: "recorded-refund-2026-11-06", mode: "recorded", domain: "refund",
  source: "deepseek-v4.1-flash-1017", target: "muse-glimmer-30b",
  status: "verified_adaptation",
  report: {
    source_training: { passed: 8, total: 8, failed: [] },
    target_training: { passed: 6, total: 8, failed: ["ineligible", "timeout_after_commit"] },
    validation: { passed: 8, total: 8, failed: [] },
    original_holdout: { passed: 7, total: 8, failed: ["timeout_after_commit"] },
    repaired_holdout: { passed: 8, total: 8, failed: [] },
  },
  evidence_url: "https://github.com/Davemafy/refit/actions/runs/42207396750",
};
const deployment: RecordedRun = {
  id: "recorded-deployment-2026-11-06", mode: "recorded", domain: "deployment",
  source: "deepseek-v4.1-flash-1017", target: "raon-1-mini-preview",
  status: "compatible_on_sample",
  report: {
    source_training: { passed: 8, total: 8 },
    target_training: { passed: 8, total: 8 },
    validation: { passed: 8, total: 8 },
    original_holdout: { passed: 8, total: 8 },
  },
};
const ready: RefitIntent = {
  intent: "model_migration", domain: "refund", source_model: refund.source,
  target_model: refund.target, missing: [], ready_for_review: true,
  requires_confirmation: true, supported_external_agents: false,
  message: "Only reviewed workflows.",
};

function fakeApi(intent = ready) {
  const api = {
    interpret: vi.fn(async (_text: string, _signal?: AbortSignal) => intent),
    runs: vi.fn(async () => [refund, deployment].map(({ id, mode, domain, source, target, status }) =>
      ({ id, mode, domain, source, target, status }))),
    run: vi.fn(async (id: string) => {
      if (id === refund.id) return refund;
      if (id === deployment.id) return deployment;
      throw new Error("not found");
    }),
  };
  return api;
}
function response(body: unknown, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(body), {
    status, headers: { "content-type": contentType },
  });
}

describe("Refit's existing API through assistant-ui's ChatModelAdapter", () => {
  it("reads actual recorded refund evidence rather than inventing a result", async () => {
    const api = fakeApi();
    const text = await answer(api, "Migrate the refund agent from DeepSeek to Muse.");
    expect(api.interpret).toHaveBeenCalledTimes(1);
    expect(api.runs).toHaveBeenCalledTimes(1);
    expect(api.run).toHaveBeenCalledWith(refund.id, undefined);
    expect(text).toContain("6/8");
    expect(text).toContain("8/8");
    expect(text).toContain("7/8 unmodified → 8/8 repaired");
    expect(text).toContain("timeout_after_commit");
    expect(text).toContain("synthetic business state");
    expect(text).toContain("built-in agent fixtures only");
  });

  it("never claims to repair a compatible migration", async () => {
    const api = fakeApi();
    const text = await answer(api, "show deployment example");
    expect(text).toContain("No repair needed or generated");
    expect(text).not.toContain("Compatibility artifact");
    expect(api.interpret).not.toHaveBeenCalled();
  });

  it("refuses to guess missing model, contract or external agent details", async () => {
    const api = fakeApi({
      ...ready, ready_for_review: false, missing: ["source_model", "target_model"],
      source_model: null, target_model: null,
    });
    const text = await answer(api, "Migrate my agent");
    expect(text).toContain("Missing or ambiguous: source_model, target_model");
    expect(api.runs).not.toHaveBeenCalled();
  });

  it("never substitutes another model's recorded scores", async () => {
    const api = fakeApi({ ...ready, target_model: "raon-1-mini-preview" });
    const text = await answer(api, "Change our refund agent to Raon from DeepSeek");
    expect(text).toContain("No verified recorded evaluation exists for this exact migration");
    expect(text).not.toContain("6/8");
    expect(api.run).not.toHaveBeenCalled();
  });

  it("does not hide backend outages behind a fake agent success response", async () => {
    const api = fakeApi();
    api.runs.mockRejectedValue(new Error("connection failed"));
    await expect(answer(api, "show refund example")).rejects.toThrow("connection failed");
  });

  it("validates business score integrity before allowing display", () => {
    const corrupted = { ...refund, report: {
      ...refund.report, source_training: { passed: 9, total: 8 },
    } };
    expect(() => assertRun(corrupted)).toThrow("Invalid source_training score");
    const incomplete = { ...refund, report: { ...refund.report, repaired_holdout: undefined } };
    expect(() => formatRecordedEvidence(incomplete)).toThrow("missing independent evidence");
  });

  it("rejects cross-origin API endpoints to keep credentials off external hosts", () => {
    expect(() => new RefitApi(fetch, "https://example.com/api")).toThrow("same-origin");
    expect(() => new RefitApi(fetch, "/api")).not.toThrow();
  });

  it("uses correct REST paths, accepts only typed JSON and sends no operator token", async () => {
    const seen: Array<[string, RequestInit]> = [];
    const transport = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      seen.push([String(url), init || {}]);
      if (String(url).endsWith("/interpret")) return response(ready);
      if (String(url).endsWith("/runs")) return response({ runs: [refund] });
      if (String(url).endsWith(refund.id)) return response(refund);
      return response({ error: "unknown" }, 404);
    }) as unknown as typeof fetch;
    const client = new RefitApi(transport);
    await client.interpret("Migrate refund from DeepSeek to Muse");
    await client.runs();
    await client.run(refund.id);
    expect(seen.map((entry) => entry[0])).toEqual([
      "/api/interpret", "/api/runs", "/api/runs/" + refund.id,
    ]);
    expect(seen[0][1].method).toBe("POST");
    expect(seen[0][1].credentials).toBe("same-origin");
    expect(seen[0][1].headers).not.toHaveProperty("Authorization");
  });
});

describe.skipIf(!process.env.REFIT_PUBLIC_URL)("Actual public Refit API integration", () => {
  it("connects to deployed Vultr service without starting paid inference", async () => {
    const origin = process.env.REFIT_PUBLIC_URL;
    if (!origin) throw new Error("REFIT_PUBLIC_URL missing");
    const transport = ((path: RequestInfo | URL, init?: RequestInit) =>
      fetch(new URL(String(path), origin), init)) as typeof fetch;
    const client = new RefitApi(transport);
    const result = await answer(client, "Migrate the refund agent from DeepSeek to Muse.");
    expect(result).toContain("6/8");
    expect(result).toContain("7/8 unmodified → 8/8 repaired");
    const compatible = await answer(client, "show deployment example");
    expect(compatible).toContain("No repair needed or generated");
  });
});
