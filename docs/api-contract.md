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
`id`, `mode` (`recorded|live`), `domain`, `source`, `target`,
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
The backend only emits verified lifecycle events (`queued`, `started`,
`complete`, `failed`): it does **not** invent progress percentages or
per-phase evaluations until the engine reports them.
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

Public live execution is **disabled by default**. It requires
`REFIT_ENABLE_LIVE=1` **and** a non-empty `REFIT_RUN_TOKEN` set on the
server, plus a bearer token provided explicitly by an authorized operator.
The token must not be embedded in the UI code. An operator-only control may
obtain it interactively without localStorage. Fixed agent adapters and
approved model IDs only; arbitrary model IDs, uploaded code, and adapter
paths are rejected. Global concurrency is 1 and a daily quota applies.
The current live adapters still execute in process: **not isolated**.

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

- These HTTP endpoints **are not** a finished Track 1 sandbox or a real
  external-agent integration.
- Natural-language `/interpret` only extracts typed options for two trusted
  built-in agents. It does not import arbitrary LangGraph/PydanticAI agents.
- The historical experiments used **real Vultr model calls**, but their
  business tools operated against isolated synthetic in-process state.
- No public endpoint can submit Python code, code repositories, arbitrary
  tool definitions, or keys.
- All user-visible containment evidence must come from a future, separately
  verified Vultr-hosted sandbox runner. No fake `blocked` counter.
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
