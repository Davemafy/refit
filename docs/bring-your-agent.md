# Bring your agent

**Refit's main workflow is open without signup:** open
https://80.240.30.92/app/agents/new, paste the URL of a public GitHub agent
or select a ZIP and inspect its original runtime. A temporary, private
visitor workspace is created automatically, with a Secure, HttpOnly cookie.
Choose original and replacement Vultr models, confirm independent tests
and authorize a real isolated migration. Review model calls, gVisor sandbox
evidence and fresh export verification from Runs. The public UI contains
no account-registration step.

Private repository imports can use an optional GitHub read token.
Credentials are never delivered to untrusted containers. Uploaded sources
and run evidence are scoped to the submitting visitor's session, not a
shared anonymous dashboard. The temporary session lasts 12 hours; keep
the same browser session to revisit its results.

Visitor sessions and migrations are rate-limited in persistent SQLite
by HMAC-hashed client address, independently of cookie rotation.
No more than three visitor migrations and 64 reserved requests per
client address per UTC day; individual visitor migration budgets must
be 1–32 requests and the root-owned global daily limit also applies.
Nginx limits request rate; the existing queue, gVisor isolation,
credential separation and sandbox cleanup requirements remain active.
Visitors can import up to three projects per temporary workspace.
An already established account continues to function but is never
required or promoted in the normal experience.

## One-click live sample (optional)

On the import page, choose **Run a live sample instead** to test Refit
without finding a repository. This runs a vetted pinned
[simonw/llm](https://github.com/simonw/llm) snapshot at
\`b9786a2daa44a995ff7719c655c5338bf685d551\`.
Unlike the recorded public examples, it consumes real Vultr inference
calls and executes the original application. A separate sample rate
limit caps automatic, preselected trials. Its results are labeled live,
then independently verified before export.

The Challenge 1 diagnostic can be triggered from a completed live
migration. The Vultr model generates Python code that executes inside
a disposable gVisor worker using sanitized migration evidence. Its
independent cross-check and cleanup receipts are shown in the existing
run inspector.

The HTTPS TLS certificate is a short-lived Let's Encrypt IP-address
certificate with an automatic renewal timer.

The externally executed zero-inference check
[`scripts/smoke_platform_https.py`](../scripts/smoke_platform_https.py)
validates TLS, public workspace pages, anonymous session mode and access rejection,
operator-token bypass rejection and certificate freshness on each main push.
After promotion, run it with `--expected-revision <full Git SHA>` to require
that the external service reports the exact installed release.
The browser sign-in-to-export acceptance was separately performed by the
operator on November 7 with two registered accounts and a Python application,
using seven real inference requests; that account-run browser artifact
has not yet been independently archived in this repository.

## Judge-facing live walkthrough

The following is the **legacy operator-only tunnel option**. Judges
should use the public HTTPS account path above; they do not need SSH or the
operator access token.

1. Using an SSH account authorized to forward ports to the Vultr VM, open
   `ssh -N -L 8098:127.0.0.1:8098 root@80.240.30.92`.
2. Open [Bring your agent](http://127.0.0.1:8098/bring). Obtain the operator token
   privately on the host from `/etc/refit/application.env`. Paste it into the
   page. The token stays in the page for this session.
3. Inspect GitHub repository `simonw/llm` at
   `b9786a2daa44a995ff7719c655c5338bf685d551`. Refit detects the Python
   CLI, model configuration seam and original `llm_version` tool.
4. Select `deepseek-v4.1-flash-1017` and `glm-5.2`. Approve the 24-request
   ceiling and click **Run migration**. Follow the real model, case, tool and
   cleanup events. Each terminal run can be reopened by its ID.
5. Download the verified configuration when the fresh export check passes.
   On failure, download the evidence and inspect the failed phase.

The operator service requires authentication and binds to loopback. The
separate public account ingress on port 443 is already deployed with HTTPS,
account scoping and SSE buffering disabled. Never expose port 8098 directly. The host installer is
`bash deploy/launch-application.sh` from a checkout under `/opt`, with Docker,
gVisor and `/etc/refit/inference.env` configured. It allows one active run,
up to 24 requests per run and 48 request slots reserved per UTC day. There
are no automatic paid retries.

## Supported import and execution

| Entry | Contract |
| --- | --- |
| GitHub | Refit reads the pinned tree, filters build output, caches and assets, then verifies the selected blobs against Git object IDs. Set an application directory or list required files under Advanced options. For private source, supply a scoped read token. Refit sends it only to the GitHub API and discards it after the request. |
| Project ZIP | Up to 32 MiB compressed, streamed to a temporary file. The selected source in either mode is limited to 12 MiB, 1,500 files and 512 KiB per file. Unsafe paths, special files and encrypted ZIP members are rejected. |
| Local CLI | `python -m scripts.application_cli /path/to/project --port 8098` imports to a locally running operator service. Set its `REFIT_APPLICATION_TOKEN`. Supply `--authorize-requests 24` to start and `--export config.json` to save a verified result. Source can stay on the developer's machine with local Docker and the same gVisor image. |

The production-verified native runtime is Python 3.11, a Python module
entry point and non-streaming OpenAI-compatible Chat Completions. The
reviewed image includes LLM 0.37.1 and its dependencies. A reviewed Node
runtime additionally supports pinned TypeScript/JavaScript CLI programs using
the Vercel AI SDK 7 tool loop and approved dependencies, without running
untrusted dependency-install scripts. It passes the original tool loop,
training, validation, holdout and fresh export with real Vultr inference
in [the paid external acceptance](https://github.com/Davemafy/refit/actions/runs/42416108155).
GLM → DeepSeek used 14 requests and verified seven gVisor cleanup receipts.
The example opts into a reusable OpenAI-compatible adapter that supplies the
schema as a final-output instruction during tool-enabled turns. The original
agent still validates structured output and executes its original tools.
The shared broker honors the response format requested by other applications. The LLM preset discovers the native CLI and uses its
`extra-openai-models.yaml` seam. Other Python agents may supply
`{"module":"agent","args":["{prompt}"],"cases":[...]}` in the form or through
`--setup setup.json`. The guided form writes `format: refit.agent.v1`
with the existing managed execution contract. Legacy JSON without a version
continues to work. Each case includes a unique `name`, a `split` of
`train`, `validation` or `holdout`, and a `prompt`. Expected behavior
can now be expressed using exact `stdout`, an object of expected
`json_contains` fields (including nested objects), a required `tool`
with optional `tool_result` and `tool_arguments`, and/or a `forbidden_tools` array.
For example: `{"name":"order","split":"train","prompt":"Find order 10","json_contains":{"status":"paid"},"tool":"get_order","forbidden_tools":["delete_order"]}`.
Fields of `json_contains` are checked by the trusted host against the original
application's parsed JSON stdout; extra fields are permitted. Required and
forbidden tool names are checked against broker-observed model tool calls.
These are bounded, declarative checks, **not** arbitrary code execution,
database invariants, HTTP service checks or verified external side effects.
When supplied, `tool_arguments` matches a subset of the broker-observed
call's JSON arguments and requires a tool response with the same call ID.
If a result is expected, it must match that same call. Use guided setup or
edit the complete JSON contract. Supply all three splits and store expected outcomes
outside the source ZIP, including any private holdout cases.
The application must honor `OPENAI_BASE_URL` and `OPENAI_MODEL`. Unreviewed TypeScript dependencies, streaming, custom provider protocols,
live external tools and persistent production services require additional
runtime support.

The app receives only the current case input. Other cases and expected
outputs remain host-side. Fresh containers give each model a clean source
snapshot and state directory. The broker sends model messages to Vultr and
keeps its credential outside the sandbox. It enforces the selected model,
request caps and a fixed inference envelope. Generic environment-seam
applications can receive compatible exports. An instruction repair requires an explicit native instruction seam.
In addition to the LLM preset, applications that **already read their system
instructions from an environment variable** can opt into
`"instruction_env":"SYSTEM_PROMPT"` and
`"instruction_base":"<the original system instruction>"` alongside
`module` or `entry`, `args`, and `cases`. Refit preserves those original
instructions and appends only a candidate supplemental instruction for
independent validation. Fresh export verification loads that configuration
into the original application runtime. This path is implemented and
unit-tested, but **has not yet demonstrated a paid independent-agent repair**.
An application without a genuine configurable instruction seam must still
report an unsupported repair rather than silently overwrite its prompts.

### Application boundaries and file state

Discovery lists candidate invocations with the nearest same-runtime manifest,
dependency names, provider signals and the evidence for its confidence.
Confirm or override the candidate before configuring a run. For an app
that needs its own working directory, reimport with its application directory
as the scope. Python and Node run in the existing managed sandbox. Developer-side
execution is available through the [connector CLI](#developer-side-connectors).

Add `state` to an evaluation case to verify application-local file effects.
Each case starts with the pinned source snapshot. Paths are relative to the
sandbox application directory. Supported operations are `exists`, `absent`,
`changed`, `unchanged` and `json_contains`. For example:

```json
{
  "name": "refund-state",
  "split": "holdout",
  "prompt": "Refund the test order",
  "state": [
    {"path": "state/order.json", "op": "changed"},
    {"path": "state/order.json", "op": "json_contains", "expected": {"status": "refunded"}},
    {"path": "state/real-payment.json", "op": "absent"}
  ]
}
```

The sandbox worker reports the observed files before and after invocation.
The evaluator holds the expected values outside the agent sandbox and
publishes file statuses, hashes and verdicts to the authenticated run.
Checks read bounded UTF-8 regular files and reject symlinks. These checks
verify local file effects, rather than database transactions or remote
business state. No external service permissions are granted.

## Use the native export

For the verified LLM run, with the original app installed at the pinned
revision, create a clean native model configuration directory:

```bash
export LLM_USER_PATH="$(mktemp -d)"
python -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["extra-openai-models.yaml"],indent=2))' app-3df57a3a263249eb-artifact.json > "$LLM_USER_PATH/extra-openai-models.yaml"
llm keys set vultr
llm prompt --no-stream --no-log --chain-limit 2 -m glm-5.2 --tool llm_version -- 'Use llm_version. Reply with only the version it returns.'
```

The configuration contains the provider URL and key alias. Supply your own
key with the original app. The Refit fresh check loaded the exported model
and arguments into the original runner with its endpoint routed through the
isolated broker.

## Live evidence · November 7, 2026

Vultr run `app-3df57a3a263249eb` started through the deployed authenticated
HTTP API at Refit revision `0d4d2bf2cf59a63eddab6b80727d8bae03090a59`.
The deployed runtime image was
`sha256:12f275f8989d1dcd68485e490f89de90d26e79436a3f1cddf92feab674c6bf92`.

| Check | Observed |
| --- | --- |
| Import | 122 files in 0.279 s, source SHA-256 `597977e191dc7e02b35ead9879958d1502b79ecb17121ad9ed8283ee43393470` |
| Runtime preparation | 0.024 s for pinned image lookup. First container start event to first inference request was 1.032 s. |
| Execution | 25.797 s and 14 Vultr requests of 24 authorized |
| Source and replacement | 3/3 each. Every partition independently matched stdout and observed the original `llm_version` tool result. |
| Export | `compatible_on_sample`, fresh GLM verification 1/1 in 3.094 s and 2 requests. No repair was needed. |
| Cleanup | All seven live gVisor containers verified absent. The separate hostile and runaway probes used zero inference, with 2/2 verified cleanup. |
| Resources | One case container at a time. Network none, unprivileged UID, read-only root, 2 CPUs, 4 GiB memory ceiling, 128 PIDs and 128 MiB temporary filesystem. |

[Live evidence](../data/evaluations/application-live-2026-11-07.json.gz) and
[host containment receipts](../data/evaluations/application-containment-2026-11-07.json)
are durable snapshots of the observed runs. The uncompressed live report
SHA-256 is `56bb71e8c483671b318b4c810a683734c2d995e486f0f8c0f560399bd5e4f212`.

The three evaluation partitions vary requests for one real tool behavior.
They do not establish compatibility for unrelated application tools or
business workflows. Igor's pinned `dev` revision
`36b3e323e79a66af86b24fd149f93cc95e7a37b1` uses the TypeScript Vercel AI SDK
ToolLoopAgent with provider routing and external services. Its execution
requires a Node runtime and offline tool and state seams. The current release
covers its source inspection, with execution blocked at setup. A repaired
regression in an independent application and a private GitHub import using
a real repository token remain unverified. The existing mini-SWE rejection
remains recorded separately.

[Engineering CI](https://github.com/Davemafy/refit/actions/runs/42352597082),
[application CI](https://github.com/Davemafy/refit/actions/runs/42352597116)
and [public acceptance](https://github.com/Davemafy/refit/actions/runs/42352597137)
passed on deployment revision `eb369028c43cdf28480862f00ea59ff32857e089`.

The deployed ZIP path accepted a one-file TypeScript fixture
(`import-7cfad4f61d3a0029`). Starting it returned HTTP 422
`setup_required` with the Python and OpenAI-compatible boundary requirement.
It used zero model requests.

## Browser acceptance · November 7, 2026

Firefox 142 ran against the deployed Vultr service through an authenticated
SSH tunnel on revision `6dbadb06a05e007e5565198b3f438ec22959f1cf`.
It rejected an invalid operator token, inspected the pinned LLM GitHub
repository and prevented a start while the authorization checkbox was clear.
Both live starts were single POSTs initiated by the browser Run button.

| Run | Input | Import | Execution | Inference | Verification |
| --- | --- | ---: | ---: | ---: | --- |
| `app-6706a75ba00f0277` | `simonw/llm`, GitHub at `b9786a2daa44a995ff7719c655c5338bf685d551` | 1.005 s | 22.271 s | 14 / 16 | Source 3/3, target 3/3, fresh native export 1/1 |
| `app-4556b7ce134da13c` | Independent electromagnetics knowledge-base CLI, uploaded ZIP, `src.qa` and no preset | 0.001 s | 18.981 s | 7 / 8 | Source 3/3, target 3/3, fresh native export 1/1 |

Both runs used `deepseek-v4.1-flash-1017` → `glm-5.2`, returned
`compatible_on_sample`, and verified cleanup for all seven gVisor
containers per run. These are model-only exports. The LLM browser observed
live tool and inference events. Its original 20-second test timeout fired
before the 22-second run finished. Firefox reopened that same run and
downloaded both outputs. The generic browser test ran start to download
with a longer deadline, then reloaded and reopened its run from the URL.
The two attempts used 21 requests against 24 authorized. The two prior
read-only browser checks did not start inference.

[LLM evidence](../data/evaluations/application-browser-llm-2026-11-07.json.gz) ·
[Generic evidence](../data/evaluations/application-browser-generic-2026-11-07.json.gz) ·
[Captured Firefox outcome](../data/evaluations/application-browser-generic-2026-11-07.jpg)

The generic ZIP contains unmodified application source and wiki files from
[`rma67274-boop/wulianwang_zuoye_mrp` at `78e234c09412cabf6a1d6f901329c5b66360d946`](https://github.com/rma67274-boop/wulianwang_zuoye_mrp/tree/78e234c09412cabf6a1d6f901329c5b66360d946).
The full repository includes a 5.1 MB PDF. Tree-based GitHub ingestion can select the agent without downloading that PDF.
A runtime-only ZIP preserves the original entry point and data. The
browser supplies three operator-owned checks for different source formulas
and page citations. The application archive excludes those checks and
runs with no app-specific adapter. Its native export sets `OPENAI_BASE_URL`
and `OPENAI_MODEL` for the original `python -m src.qa` command. Use your
own API key when applying it locally. The deployed live broker used isolated
loopback endpoints for the original-runtime check.

Reproduce the archive without touching production state:

```bash
git init qa-source
git -C qa-source fetch --depth=1 https://github.com/rma67274-boop/wulianwang_zuoye_mrp.git 78e234c09412cabf6a1d6f901329c5b66360d946
git -C qa-source archive --format=zip FETCH_HEAD src/qa.py wiki test_all_features.py > qa-agent.zip
```

The tested ZIP SHA-256 is
`ff329acccdc47917ab9e951fb39d88762d0a31bd58fae6694f2724905a26d980`.
The normalized source digest is
`sha256:d5245d53b14cb6fcff6ac47992b5b069861033b8d1d4f210cf265c8b2c1488a3`.

With the private tunnel open, the recorded walkthrough can use either run
ID above without spending inference. The [browser harness](../tests/browser_application.mjs)
repeats the LLM import, checks authorization and downloads the saved run by
default. Set `REFIT_APPLICATION_TOKEN` locally. Use
`REFIT_BROWSER_REOPEN=app-6706a75ba00f0277` for the browser-started LLM run.
Only pass `--execute` (16 requests) or `--execute-generic` with
`REFIT_GENERIC_ZIP=/path/to/qa-agent.zip` (8 requests) after reserving the
budget. The verified deployment uses a private tunnel for operator
demonstrations. Public evidence and authenticated execution remain separate.

The [Figma architecture](https://www.figma.com/design/jh0XDbYZzwv90vAOnWw0Zu/Untitled?node-id=56-2)
guided the persistent run ID and outcome/evidence separation. The recorded-only
board predates this live service. Both verified compatibility and verified
repair may export when fresh native verification passes.


## TypeScript tool-loop acceptance: extended fifth step

The paid GLM TypeScript run reported four consecutive \`read_file\` calls and
stopped at Refit's old four-completion per-case cap. That result **does not**
establish that a fifth model completion would succeed. The revised runner
allows eight completions per case within bounded run and sandbox deadlines.
It emits a diagnostic event after four identical read-only calls without
changing the tool outcomes or granting an export. Unsafe and state-changing
tool calls are not treated as read-only repeats.

The zero-inference gVisor acceptance now includes a separate scripted broker
that returns four identical file reads followed by a valid structured response
on the fifth original AI SDK step. All seven native sandbox executions and
fresh export checks must pass to prove that Refit does not truncate this
legitimate five-step behavior. This is **not a claim of paid GLM success**.
The real paid comparison remains an open acceptance check. Avoid replaying
a failure without examining its event evidence.

## Developer-side connectors

Use an operator-controlled Linux test machine. Supply `VULTR_INFERENCE_API_KEY`
in the connector process environment. The broker keeps it outside the agent
and grants a one-case loopback token that authorizes only the selected model
within the approved request budget.

```bash
python -m scripts.application_connector ./my-project \
  --setup ./cases.json --python /absolute/path/to/venv/bin/python \
  --allow-local-execution --authorize-requests 8 --evidence ./run.json
```

The local Python connector copies a bounded source snapshot to a fresh work
directory per invocation. Only run code you trust with the permissions of your
user account. The connector cleans up its worker and temporary workspace. It
does not contain arbitrary network access or filesystem writes outside that
workspace.

For an existing test service, pass `--test-service http://127.0.0.1:9000/invoke`,
`--service-revision <revision>` and `--allow-isolated-test-service` in place of
the project and local-execution options. Set a scoped `REFIT_SERVICE_BEARER` in
the connector environment. The endpoint accepts a POST with `prompt`, `model`,
`base_url` and a temporary `api_key`, and returns `{"output": ...}` with
text or a JSON object. The developer authorizes calls to this endpoint and
confirms fresh test state for every invocation. Service mode verifies output
and observed tool messages. It rejects file-state assertions because the
service's filesystem is outside the connector's observation boundary.
The CLI blocks non-loopback destinations and redirects.

Both modes use the existing training, validation, holdout and fresh
verification gates. A successful run writes the portable configuration to
the private evidence file. Apply its model environment to the original
invocation or pass its model and base URL to the service with your own
provider credential. The service revision is supplied by its operator.

## One-shot paid TypeScript acceptance (external GitHub runner)

The explicit request in
`experiments/ai-sdk-file-agent/live-acceptance-request.json` is the sole
push-trigger for `.github/workflows/live-application-typescript.yml`.
It checks for `VULTR_INFERENCE_API_KEY` in GitHub Actions secrets, builds the
pinned upstream AI SDK agent into a fresh `runsc` runtime, and authorizes
**at most 48 paid Vultr requests** for one DeepSeek-to-GLM migration. The
result, including failures, per-case tool/state outcomes, export eligibility
and container cleanup receipts, is saved as a seven-day workflow artifact.
Missing credentials cause an explicit skip without any paid requests. This
execution is **external runner evidence**, not proof the production Vultr
service has deployed this Git revision. It must not be represented as a
successful paid TypeScript migration unless the recorded source, target,
original-runner fresh export and all cleanup checks actually pass.


### First paid external AI SDK acceptance: November 7, 2026

[GitHub Actions run 42404568194](https://github.com/Davemafy/refit/actions/runs/42404568194)
executed DeepSeek as source and GLM as replacement through the original
TypeScript AI SDK application. The **source baseline failed after one
paid request**: the first \`order\` case did not call the required
\`read_file\` tool. File-state checks and the single sandbox cleanup
passed; the export was correctly withheld. The GLM replacement was
**not evaluated**. This is a genuine source-baseline failure, not a
quota exhaustion or a successful TypeScript migration.

The next acceptance request switches the model order to GLM → DeepSeek.
That isolates whether a fifth original-agent step can complete after
the previously observed four repeated GLM file reads. Its outcome must
be evaluated independently and cannot be inferred from the earlier
zero-inference test.

### Second paid external AI SDK acceptance: November 7, 2026

[GitHub Actions run 42404961771](https://github.com/Davemafy/refit/actions/runs/42404961771)
reversed the models (GLM source, DeepSeek replacement) under the new eight-call
per-case Refit ceiling. On the first \`order\` case, **GLM called \`read_file\`
five times** and the original AI SDK agent exited without a usable final
structured result (\`application_exited\`). The required tool was genuinely
observed and file-state assertions passed. All observed sandbox cleanup
receipts were verified. Only five requests were used; no export was produced
and DeepSeek was not tested in this direction.

Together with the first paid attempt, the results distinguish a skipped tool
call from a repeated tool loop. The new extended-loop test broker proves
Refit can transport a valid fifth-step completion, but **the paid GLM model
did not deliver that completion**. A credible repair needs an explicit
native, exportable adaptation seam plus fresh independent verification, not
a forced success label or relaxed oracle. Further automatic billable retries
are disabled until that adaptation is implemented and assessed.
