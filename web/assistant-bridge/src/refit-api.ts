/**
 * Typed same-origin REST client. Refit's Python service remains authoritative:
 * a frontend message never becomes permission to execute a paid migration.
 */
export type AgentDomain = "refund" | "deployment";
export type MigrationStatus =
  | "verified_adaptation"
  | "compatible_on_sample"
  | "source_baseline_insufficient"
  | "candidate_failed_validation"
  | "candidate_failed_holdout"
  | "queued"
  | "running"
  | "execution_error"
  | "diagnostic_verified"
  | "diagnostic_failed"
  | string;

export interface RefitIntent {
  intent: "model_migration";
  domain: AgentDomain | null;
  source_model: string | null;
  target_model: string | null;
  missing: string[];
  ready_for_review: boolean;
  requires_confirmation: boolean;
  supported_external_agents: boolean;
  message: string;
}

export interface Evaluation {
  passed: number;
  total: number;
  unsafe_attempts?: number;
  failed?: string[];
}
export interface MigrationReport {
  source_training?: Evaluation;
  target_training?: Evaluation;
  validation?: Evaluation;
  original_holdout?: Evaluation;
  repaired_holdout?: Evaluation;
}
export interface RecordedRun {
  id: string;
  mode: "recorded";
  domain: AgentDomain;
  source: string;
  target: string;
  status: MigrationStatus;
  report: MigrationReport;
  evidence_url?: string;
  caveat?: string;
  artifact_filename?: string;
}
export interface RunListItem {
  id: string;
  mode: string;
  domain: AgentDomain;
  source: string;
  target: string;
  status: string;
  evidence_url?: string;
}
function isObject(item: unknown): item is Record<string, unknown> {
  return typeof item === "object" && item !== null && !Array.isArray(item);
}
function assertPhase(value: unknown, key: string): asserts value is Evaluation {
  if (!isObject(value)) throw new Error("Invalid " + key + " evidence");
  const { passed, total, failed } = value;
  if (
    !Number.isInteger(passed) || !Number.isInteger(total) ||
    (passed as number) < 0 || (total as number) < (passed as number) ||
    (total as number) > 1000
  ) throw new Error("Invalid " + key + " score");
  if (
    failed !== undefined &&
    (!Array.isArray(failed) ||
      !failed.every((x) => typeof x === "string" && x.length <= 100))
  ) throw new Error("Invalid " + key + " failures");
}
export function assertRun(value: unknown): asserts value is RecordedRun {
  if (!isObject(value)) throw new Error("Invalid Refit run");
  if (
    typeof value.id !== "string" ||
    !/^[a-z0-9-]+$/.test(value.id) ||
    !["refund", "deployment"].includes(String(value.domain)) ||
    typeof value.status !== "string" ||
    typeof value.source !== "string" ||
    typeof value.target !== "string" ||
    !isObject(value.report)
  ) throw new Error("Invalid Refit run shape");
  const report = value.report;
  for (const key of [
    "source_training", "target_training", "validation",
    "original_holdout", "repaired_holdout",
  ]) {
    if (report[key] !== undefined && report[key] !== null) {
      assertPhase(report[key], key);
    }
  }
  if (!report.source_training || !report.target_training) {
    throw new Error("Run missing source/target evidence");
  }
}
export class RefitApi {
  constructor(
    private readonly transport: typeof fetch = (input, init) => globalThis.fetch(input, init),
    private readonly prefix: string = "/api",
  ) {
    if (!/^\/api$/.test(prefix)) {
      throw new Error("Refit must use the same-origin /api endpoint");
    }
  }
  private async json(path: string, init: RequestInit = {}): Promise<unknown> {
    const response = await this.transport(this.prefix + path, {
      ...init, credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", ...init.headers },
    });
    if (!response.ok) {
      throw new Error("Refit API returned HTTP " + response.status);
    }
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("Refit API returned a non-JSON response");
    }
    return response.json() as Promise<unknown>;
  }
  async interpret(text: string, signal?: AbortSignal): Promise<RefitIntent> {
    const value = await this.json("/interpret", {
      method: "POST", signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (
      !isObject(value) || value.intent !== "model_migration" ||
      !Array.isArray(value.missing) ||
      typeof value.ready_for_review !== "boolean" ||
      !("domain" in value) ||
      !("source_model" in value) ||
      !("target_model" in value)
    ) throw new Error("Refit returned an invalid migration intent");
    return value as unknown as RefitIntent;
  }
  async runs(signal?: AbortSignal): Promise<RunListItem[]> {
    const response = await this.json("/runs", { signal });
    if (!isObject(response) || !Array.isArray(response.runs)) {
      throw new Error("Refit returned an invalid run index");
    }
    return response.runs.filter((item): item is RunListItem =>
      isObject(item) &&
      typeof item.id === "string" && /^[a-z0-9-]+$/.test(item.id) &&
      ["refund", "deployment"].includes(String(item.domain)) &&
      typeof item.status === "string" &&
      typeof item.source === "string" &&
      typeof item.target === "string" &&
      item.mode === "recorded",
    );
  }
  async run(id: string, signal?: AbortSignal): Promise<RecordedRun> {
    if (!/^[a-z0-9-]+$/.test(id)) throw new Error("Invalid run id");
    const value = await this.json("/runs/" + encodeURIComponent(id), { signal });
    assertRun(value);
    if (value.mode !== "recorded") {
      throw new Error("This bridge only displays verified recorded outcomes");
    }
    return value;
  }
}
