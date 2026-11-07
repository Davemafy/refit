# Refit

**Change the model. Keep the behavior.**

## Bring Your Agent — live application

The **public HTTPS application** is at **https://80.240.30.92/app**.
Anyone can explore its workspace and review a sanitized, real November 7
Python migration without signing in. The guest experience is read-only:
no private projects, sandbox launches, or billable inference are exposed.
It is separate from the read-only HTTP evidence site. Registered developers
can import pinned public GitHub repositories or ZIP archives, configure
evaluation cases, authorize a bounded live migration, inspect run evidence and
download a native export only after fresh verification. Projects, runs, streams,
evidence and exports are isolated per account. The Vultr inference key remains
on the host; imported code runs in disposable gVisor containers.

The **verified production Python 3.11 path** supports non-streaming
OpenAI-compatible Chat Completions. Two browser-initiated, independently
verified Python examples and original-runtime exports are recorded in the
[application engineering guide](docs/bring-your-agent.md). A reviewed
**Node/TypeScript + AI SDK 7** runtime now passes the original upstream tool
loop and native-export check with a zero-inference test broker. Its first
paid DeepSeek evaluation **failed** the required read-file behavior and
correctly produced **no export**. TypeScript model compatibility is not
yet proven by a successful paid migration.

Signup is open without an invitation. Importing your own source and
running live migrations requires signing in, and is subject to per-account
and global inference budgets. There is **no anonymous billable execution**.
See [HTTPS signup and judge access](docs/bring-your-agent.md#public-https-account-access).

Refit finds and repairs tool-use regressions when migrating an AI agent to a
different language model. It compares actual stateful outcomes, proposes
bounded model-facing changes, and tests them against independent scenarios.

## Developer entry point

Use the [developer MVP guide](docs/developer-mvp.md) for the live migration CLI,
patch application, fixed-patch verification, optional external agent runner,
and the public evidence API. UI replacement is independent of these interfaces.

For an independently developed agent, use the
[original retail-agent integration](integrations/retail/README.md). It runs the
upstream agent, customer simulator, tools, database and evaluator inside gVisor,
then exports configuration that can be loaded in its original framework.
The [real comparison and exported-runner evidence](docs/original-retail-agent-evidence-2026-11-07.md)
shows source **6/6**, replacement GLM **6/6**, and a fresh exported-configuration
check **2/2**. This model pair needed no instruction repair. The complete effort
used **241 real Vultr requests**, below its declared 400-request ceiling.

The exported refund patch has now been applied through the original external
τ-bench agent runner and tested on three predeclared fresh seeds: source 24/24,
unchanged Muse 13/24, patched Muse 24/24, with zero unsafe attempts. The run also
passed three original upstream task fixtures on both models and used 201 real
Vultr inference requests. See [complete framework evidence](docs/framework-evidence-2026-11-06.md).
The [public Vultr evidence API](http://80.240.30.92) passed an independent nine-route
HTTP check; its public paid actions remain disabled.

The [recovered Vultr-host frozen-patch test](docs/vultr-frozen-patch-recovery-2026-11-06.md)
passed **8/8 patched vs. 5/8 unchanged Muse**, with source 8/8, zero unsafe
attempts, 63 inference requests, and all 24 gVisor workers cleaned up. The raw
report, operator wrapper, containment probes and recovery checks are preserved.
This is separate from the published host run that correctly rejected a new
candidate during validation.

## Run the working demo

Refit includes a **zero-build evidence demo** at `/` and `/demo` using
its same-origin Python API. It shows the actual recorded Vultr evaluations,
natural-language migration interpretation, and independently validated
patch export. The separate frontend workstream can replace the root page
later without changing `/api/*` or `/demo`.

From the existing Vultr Ubuntu VM, as root:

```bash
cd /opt/refit-app
git pull --ff-only
bash deploy/launch-public.sh
```

The launcher runs tests, installs a restricted systemd service and Nginx
reverse proxy, verifies HTTP health, and leaves all paid inference disabled
until an authenticated HTTPS operator workflow is provisioned. After
deploying, run `python3 -m scripts.smoke_public --url http://YOUR_VULTR_IP`
from another computer. Full instructions: [public deployment](docs/public-deployment.md).

The [external acceptance](docs/vultr-host-acceptance-2026-11-06.md) checks the
public service against its exact deployed startup revision.

## Real inference on Vultr, without an exposed paid endpoint

The backend now saves live run records **before** making paid model calls
and persists observed evaluation stages, event cursors and outcomes. A
restarted server restores completed records and marks interrupted work
explicitly; it never automatically replays a paid migration.

For one genuine live evaluation on the Vultr VM, use the
[operator migration runbook](docs/live-operator-run.md).
The operator-only CLI requires an explicit `--execute` flag, checks that
`runsc` is registered, runs built-in business tools under gVisor,
and refuses to approve a migration if containment/cleanup proof is absent.
The optional `--publish` flag copies **finished evidence** into the
unprivileged public API without enabling browser-side inference.

The **HTTP evidence site** remains read-only, including paid actions. The
separate **HTTPS account application** now supports authenticated live Python
imports, original-runtime verification and export. The synthetic business
agents are independently tested engine examples, not the public application's
entire compatibility scope. The [external CLI](integrations/retail/README.md)
continues to support the reviewed retail agent.

## Current engine — one implementation, two independent agent domains

Refit's contract-driven engine now supports **refund workflows** and
**deployment incident recovery** through separate adapters and protected
stateful business verifiers.

A new live Vultr experiment through the **shared migration engine** produced
`verified_adaptation`: DeepSeek source 8/8, unmodified Muse target 6/8,
generated-instruction Muse 8/8 training, 8/8 independent validation, and
8/8 holdout (vs 7/8 unmodified). No unsafe refund attempts; 134
real model requests. See [run #42207396750](https://github.com/Davemafy/refit/actions/runs/42207396750).

The independent deployment agent returned `compatible_on_sample` for
DeepSeek → Raon: 8/8 training, 8/8 validation and 8/8 holdout, zero
unsafe rollback attempts, 126 inference requests.
[Deployment run #42206326304](https://github.com/Davemafy/refit/actions/runs/42206326304).

See the [shared-engine evidence and evaluator bug postmortem](docs/shared-engine-evidence-2026-11-06.md).
This is empirical success on two supported synthetic agents; it is
**not** a universal agent-migration guarantee.

## Live evidence — first verified repair

On November 6, 2026, Refit reproduced and repaired a regression in an
order-refund agent using real **Vultr Serverless Inference** calls.

| Gate | Result |
| --- | ---: |
| DeepSeek V4.1 Flash, source training | 8/8 |
| Muse Glimmer 30B, unmodified target training | 5/8 |
| Muse after generated instructions + lookup guard | **8/8** |
| Independent validation | **8/8** |
| Unmodified Muse on holdout | 7/8 |
| Repaired Muse on holdout | **8/8** |
| Unsafe refund attempts | **0** |

The run used 129 inference requests and the execution report says
`verified_repair`. See [the successful GitHub Actions run](https://github.com/Davemafy/refit/actions/runs/42193722623)
and [methodology, earlier failures and limitations](docs/live-evidence-2026-11-06.md).

For the engineering rationale, repair operators, verification limits and
next cross-domain falsification test, read the
[core thesis and proof plan](docs/core-thesis-and-proof-plan.md).

The accepted adaptation combined an **AI-generated instruction rewrite** with
an evidence-triggered first-tool selection request for `get_order`.
The independent SQLite gateway and verifier did not change.

**Follow-up causal ablations on two fresh seeds found that the generated
instructions alone passed 8/8 in both runs, whereas the lookup setting alone
passed 5/8.** The provider sometimes returned no tool call despite the
requested named tool; it is not an enforcement guarantee. See
[the two-run ablation evidence](docs/causal-ablation-evidence-2026-11-06.md).

This historical experiment covers one synthetic agent. Subsequent framework
and [Vultr-host evidence](docs/vultr-frozen-patch-recovery-2026-11-06.md) extend
that evidence without establishing general agent-migration reliability.

## UI integration contract (current development work)

Refit now exposes a tested, **same-origin JSON backend API** for the separate
frontend workstream. It serves two preserved genuine Vultr experiment reports,
returns conservative natural-language migration intents for the supported
workflows, and provides verified compatibility JSON downloads.

```bash
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./var/runs
curl -fsS http://127.0.0.1:8097/api/capabilities
curl -fsS http://127.0.0.1:8097/api/runs
```

The exact endpoint shapes, error codes and integration smoke tests are in
[the authoritative frontend API contract](docs/api-contract.md).

**Boundaries:** natural-language parsing is limited to the two built-in
agents; public external-agent imports remain unsupported. The isolated
external-agent CLI is documented separately. Built-in refund and
deployment tools now have an **opt-in isolated Docker/gVisor execution path**
using one disposable worker per scenario. A separate path runs real
Vultr-model-generated migration diagnostic Python in another worker.
Live calls require explicit server flags and an operator token.
[Host execution evidence](docs/vultr-frozen-patch-recovery-2026-11-06.md) is
preserved separately from CI and from the public read-only service.

## Executing generated diagnostics safely

Refit's **supplementary code-writing step** can ask Vultr Serverless Inference
to generate a migration diagnostic program and execute that Python in a
disposable sandbox, while a protected host-side oracle independently checks
the results. It cannot approve a business migration by itself.

A dedicated [gVisor test workflow](.github/workflows/gvisor-verify.yml)
installs the signed upstream `runsc` runtime and tests real Python execution,
denied outbound network/DNS, absent credentials, read-only root filesystem,
hash-chained execution events, and verified container cleanup. The same tests
also run with ordinary Docker for comparison. See
[the sandbox runbook](docs/sandbox-runtime.md), the operator-gated
[API contract](docs/api-contract.md), and the
[Vultr-host installation and verification scripts](deploy/).

**Deployment distinction:** GitHub runner containment tests do not establish
that gVisor is installed on our Vultr VM. When
`REFIT_USE_TOOL_SANDBOX=1`, the shared migration engine routes real tool calls
to ephemeral, networkless Docker workers. The original in-process mode remains
for legacy experiments and offline tests. All model requests and compatibility
patch approvals stay with the host. This bridge is verified by CI on GitHub's
Docker runner and exercised on Vultr in the
[recovered fixed-patch verification](docs/vultr-frozen-patch-recovery-2026-11-06.md). No arbitrary
agent-code uploads are exposed through the API.

## Code

- `scripts/migration_engine.py` — shared contract-driven replay, diagnosis,
  bounded repair search and independent verification.
- `scripts/refund_adapter.py` and `scripts/deployment_incident_probe.py` —
  separate stateful tool environments and business invariants.
- `scripts/refit_cli.py` — run a supported or trusted locally imported agent
  adapter against live inference and produce an evidence report.
- `scripts/compatibility_artifact.py` — export a model-scoped patch and verify
  immutable contract/configuration fingerprints (not a digital signature).
- `scripts/refit_vultr_probe.py` — historical baseline Vultr experiment.
- `scripts/refit_stress_probe.py` — eight adversarial, stateful workflow
  scenarios with independent verification and selective repair.
- `tests/` — offline unit tests and deterministic protocol simulations.
- `.github/workflows/ci.yml` — builds and tests on Python 3.11 and 3.12.
- `.github/workflows/live-experiment.yml` — explicitly gated, bounded real
  Vultr inference experiment with a private Actions secret.
- `docs/architecture.md` — system boundary, requirements and limitations.

No dependency installation is required for the experiment CLI.

## Test

Run on Python 3.11+:

```bash
python3 -m unittest discover -s tests -p 'test_refit*.py' -v
```

## Run the real experiment

Set `VULTR_INFERENCE_API_KEY` privately, or keep it in a root-only server
file at `/etc/refit/inference.env`. **Never commit or paste an API key into
issues or CI logs.**

```bash
python3 -m scripts.refit_cli \
  --domain refund \
  --source deepseek-v4.1-flash-1017 \
  --target muse-glimmer-30b \
  --repair deepseek-v4.1-flash-1017 \
  --max-requests 160 \
  --output refit-migration-report.json \
  --export-patch refit-compatibility.json
```

Use `--domain deployment` to run the independent deployment responder.
Use `--adapter trusted.module` only with locally reviewed Python code:
adapter imports are **not sandboxed** and must not be offered to public users.

On a verified adaptation, the CLI exports a reviewable JSON patch bound to
the target model and original approved contract. A developer must explicitly
approve and apply it; Refit never silently changes a production agent.

Vultr inference calls are billable. The report contains only synthetic
orders, model-generated instructions and traced tool calls. Refit checks that
the actual returned model matches the requested model.

## Trust and correctness

- Built-in agents have declared tools; refunds use `get_order` and
  `issue_refund`, while deployment recovery uses four independent tools.
- The gateway enforces identity, eligibility, exact minor-currency-unit
  refund amounts, and idempotency. It never touches real customer accounts.
- Model prose isn't the oracle: Refit checks the transaction database state,
  tool call sequence, authorized outcomes and fresh holdout cases.
- The shared engine permits bounded instruction and tool-description patches.
  Historical probes also tested a first-tool request, but the provider did
  not always honor it; it must not be mistaken for hard enforcement.
  Patches cannot edit the evaluator or protected business invariants.
- The historical business tool runs used in-process SQLite simulations.
  An opt-in migration path now isolates the trusted built-in tool environments
  in fresh, networkless Docker containers, validated against the original
  stateful oracle in GitHub CI. Generated diagnostics have a separate isolated
  execution path. This is not a universal external-agent sandbox. Host-specific
  Vultr containment and fixed-patch verification are recorded in the
  [host evidence](docs/vultr-frozen-patch-recovery-2026-11-06.md).

## Remaining work

1. Broaden repeated evaluation to unseen workflow families and independently
   operated customer agents, beyond the three-seed framework result above.
2. Build the minimal judge-facing workflow and Vultr-hosted control plane.
3. Preserve the known deployed revision and reproduce external read-only
   acceptance before submission; host containment evidence is now archived.
4. Publish the reproducible demo, video and submission evidence.

This is the **Refit product repository**. The separate dev-mcp service is a
development tool, not part of the shipped product.

MIT licensed.
