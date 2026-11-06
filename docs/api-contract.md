# Refit frontend ↔ backend contract (v1)

**Authoritative integration contract — implement the UI against these endpoints.**
This is not a visual design brief. The existing engine, model calls and recorded
run evidence are the sources of truth. Do not simulate progress or hardcode UI
numbers that disagree with this API.

## Run locally

From the repository root:

```sh
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./var/runs
```

No dependencies, keys, or live model spending required to load the API and
two archived real-Vultr experiments.

For production: serve the frontend and `/api/*` on the **same origin** via a
reverse proxy. Leave the Python API bound to 127.0.0.1. Never embed the Vultr
inference API key or operator token in the frontend bundle.

## Endpoint contracts

`GET /api/health` → 200

```json
{"status":"ok","service":"refit","contract_version":"v1"}
```

This proves the HTTP service is responding, **not** that a sandbox or live
provider is healthy.

The response also includes `revision`: `commit` (a validated Git SHA or null),
`tracked_files_clean` (boolean or null), and `captured_at`. This is captured once
when the service starts; pulling new files cannot relabel an older running
process. Each newly accepted live run retains the same `engine_revision`.
Use the exact deployed SHA for external acceptance checks. Unknown provenance
must not be displayed as a verified release.

`GET /api/capabilities` → 200. Source of truth for workflow picker and model
picker. Fields: `contract_version`, `domains`, `models`,
`recorded_runs`, `live_runs_enabled`, `external_agent_import`,
`sandbox`, `warnings`.

`POST /api/interpret` with `{"text": "Move our refund agent from DeepSeek to Muse"}`
→ 200:

```json
{
  "intent":"model_migration",
  "domain":"refund",
  "source_model":"deepseek-v4.1-flash-1017",
  "target_model":"muse-glimmer-30b",
  "missing":[],
  "ready_for_review":true,
  "requires_confirmation":true,
  "supported_external_agents":false,
  "message":"Review these options before running. Only two built-in agent workflows are currently supported; this does not import your agent."
}
```

This is **conservative entity extraction for two known agent workflows**,
not a conversational LLM planner. If a request is ambiguous, `missing`
contains typed fields requiring user selection. The endpoint cannot import
external agents, generate Python, or initiate inference. **Never automatically
start a run in response to `/api/interpret`; the user must confirm first.**

`GET /api/runs` → `{"runs":[...items]}`. Each item contains:
`id`, `mode` (`recorded|live|live_diagnostic`), `domain`, `source`, `target`,
`status`, `evidence_url` (optional), and `created_at` (optional).
The two recorded run IDs are:

- `recorded-refund-2026-11-06`: source training 8/8,
  unmodified target 6/8, adapted training 8/8, validation 8/8,
  unmodified holdout 7/8, adapted holdout 8/8, 134 real model
  requests. Evidence: GitHub Actions run `42207396750`.
- `recorded-deployment-2026-11-06`: source training 8/8,
  target training 8/8, independent validation 8/8, holdout 8/8.
  **No repair generated.** Evidence: GitHub Actions run `42206326304`.

All counts come from preserved real Vultr inference results against
**synthetic business state**, not from fabricated frontend fixtures.

`GET /api/runs/{id}` → full run detail: includes `mode`, `domain`,
`source`, `target`, `status`, `report`, `patch` (nullable), and
where available `model_requests`, `evidence_url`, `caveat`,
`execution_isolation`.

`GET /api/runs/{id}/artifact` → **full validated compatibility JSON**
for a run with `verified_adaptation`. The backend checks the artifact
integrity digest, target model, original configuration fingerprint, and
protected business contract before serving it. Returns 404
`artifact_not_found` for a run with no verified patch (e.g. a compatible
deployment agent). Use this endpoint for the UI's **Export compatibility
patch** action; never invent an export from the preview string.

For a verified adaptation, display `report.source_training`,
`report.target_training`, `report.trials`, `report.validation`,
`report.original_holdout` and `report.repaired_holdout`.
Never display a numerical outcome unless the corresponding field exists.
Do not label `compatible_on_sample` as a repaired failure.

`GET /api/runs/{id}/events?after=0` → 200:

```json
{
  "run_id":"recorded-refund-2026-11-06",
  "events":[{"seq":1,"type":"recorded","at":"2026-11-06","message":"Imported from a verified historical run"}],
  "next_after":1,
  "terminal":true
}
```

Events are **JSON polling**, not Server-Sent Events (SSE).
While a live run runs, poll every 2–4 seconds with `after=last_seq`.
The backend emits durable lifecycle events (`queued`, `started`,
`complete`, `failed`, `interrupted`) and **measured engine events**
(`phase_started`, `phase_completed`, `repair_started`,
`repair_generated`). A completed phase includes its actual
`details.phase`, `details.model`, `details.passed`, `details.total`
and `details.unsafe_attempts`. No synthetic percentages are sent.

The service stores each live run and its entire event sequence atomically
before executing paid requests. On restart it restores completed outcomes,
cursor positions and daily quota. Incomplete runs become
`execution_interrupted`: no automatic retry, no approved patch.
When `terminal=true`, refresh `GET /api/runs/{id}`.

`POST /api/runs` requires operator authorization:

```http
Authorization: Bearer <operator-supplied secret>
Content-Type: application/json
```

```json
{"domain":"refund","source_model":"deepseek-v4.1-flash-1017","target_model":"muse-glimmer-30b"}
```

→ 201:

```json
{"id":"live-<opaque-id>","status":"queued","events_url":"/api/runs/live-<opaque-id>/events"}
```

An alternate operator-only SSH workflow can execute a full live
migration and publish its **terminal evidence** into the existing public
read-only API, without enabling a privileged browser endpoint. See
[the Vultr operator runbook](live-operator-run.md).

Public live execution is **disabled by default**. It requires
`REFIT_ENABLE_LIVE=1` **and** a non-empty `REFIT_RUN_TOKEN` set on the
server, plus a bearer token provided explicitly by an authorized operator.
The token must not be embedded in the UI code. An operator-only control may
obtain it interactively without localStorage. Fixed agent adapters and
approved model IDs only; arbitrary model IDs, uploaded code, and adapter
paths are rejected. Global concurrency is 1 and a daily quota applies.
The default live path uses in-process trusted business tools. Operators can
enable `REFIT_USE_TOOL_SANDBOX=1` to route all migration tool operations through
disposable restricted Docker workers. The model client, host control plane and
approved repair gate stay outside the worker. This bridge has passed actual
GitHub Docker integration tests; Vultr VM verification is still pending.

## Operator-only sandbox diagnostic

POST /api/runs/{recorded_id}/diagnose (JSON body {}, Bearer operator token)
returns 201 with a new diagnostic run ID and events URL.

This endpoint is enabled only when REFIT_ENABLE_LIVE=1,
REFIT_ENABLE_SANDBOX_DIAGNOSTICS=1, REFIT_RUN_TOKEN is set,
and the operator authenticates. It accepts no arbitrary Python, model IDs,
adapter uploads or repository URLs. It costs at most one real Vultr inference
request and uses the same daily quota and one-at-a-time global concurrency.

The backend asks Vultr inference to produce Python that examines the archived
migration evidence, executes it inside Docker, checks the program's JSON
against a protected independent host oracle and returns execution evidence.

Poll GET /api/runs/{id}/events?after=N, then GET /api/runs/{id}.
New run mode: live_diagnostic. Terminal statuses: diagnostic_verified
and diagnostic_failed. The response may contain sandbox_diagnostic with:
generated_code, expected, observed, verified, validation_error, sandbox.
Sandbox includes stdout, stderr, exit_code, ledger, ledger_valid, runtime,
container_created, container_removed_verified and resource restrictions.

The original archived migration remains unchanged. This diagnostic action
isolates only its generated diagnostic program. Independently, opt-in
`REFIT_USE_TOOL_SANDBOX=1` isolates the built-in refund/deployment tool
simulations for full live migration runs. This does not support uploaded
external agents or isolate the host-side inference client.

GET /api/capabilities provides sandbox.generated_python_diagnostics_enabled,
sandbox.business_tools_sandbox_configured, sandbox.runtime and
sandbox.business_tools_isolation_verified_on_vultr_vm. Configuration alone
is not proof of successful containment; actual run records contain
`report.execution_boundary` and `execution_isolation`. Do not display
a verified Vultr sandbox label without Vultr-host evidence.

Security: Never embed the operator token in client source or localStorage.
An authenticated operator can supply it interactively for the demo.

See docs/sandbox-runtime.md for the exact VM commands, Docker policy,
and the distinction between GitHub-runner proof and Vultr-VM proof.

## Error response contract

```json
{"error":{"code":"daily_limit","message":"Daily live-run allowance reached."}}
```

Status codes:
- 400 malformed JSON;
- 401 operator authorization missing or incorrect;
- 404 missing route or run;
- 409 another live run already running;
- 413 payload exceeds 4 KiB;
- 415 JSON Content-Type required;
- 422 unsupported domain/model, ambiguous/invalid request or cursor;
- 429 daily live quota exhausted;
- 503 live inference is disabled.

The UI must remain usable with recorded runs when live execution is
disabled or fails. Show actual API errors; don't present recorded
results as a freshly completed run.

## Security and truthful claims

- These endpoints are not a verified Vultr-hosted Track 1 product deployment
  or a general external-agent integration.
- Natural-language `/interpret` only extracts typed options for two trusted
  built-in agents. It does not import arbitrary LangGraph/PydanticAI agents.
- The historical experiments used **real Vultr model calls**, but their
  business tools operated against isolated synthetic in-process state.
- No public endpoint can submit Python code, code repositories, arbitrary
  tool definitions, or keys.
- Actual GitHub Docker containment and real tool-worker parity have passed.
  Do not present those as Vultr-host verification. No fake `blocked` counter.
- Separate workstreams can build UI and sandbox runner without touching
  each other's files; integrate against this API and add cross-boundary tests.

## Reproduction and regression check

```sh
python3 -m unittest discover -s tests -p 'test_refit*.py' -v
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./var/runs
curl -fsS http://127.0.0.1:8097/api/health
curl -fsS http://127.0.0.1:8097/api/capabilities
curl -fsS http://127.0.0.1:8097/api/runs
curl -fsS http://127.0.0.1:8097/api/runs/recorded-refund-2026-11-06
```

**Front-end handoff requirement:** show recorded evidence from this API
before building around a live run. End-to-end browser smoke tests must
load the real frontend, fetch `/api/runs`, inspect a verified migration
and confirm its numbers against the JSON. A green frontend build alone
is not integration proof.
