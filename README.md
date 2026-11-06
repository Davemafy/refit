# Refit

**Change the model. Keep the behavior.**

Refit finds and repairs tool-use regressions when migrating an AI agent to a
different language model. It compares actual stateful outcomes, proposes
bounded model-facing changes, and tests them against independent scenarios.

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

**Public deployment is not asserted until its external URL is tested.**

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

The public site remains read-only until HTTPS and properly authenticated
server-side job submission exist. These reviewed synthetic business agents
are not imported third-party agents.

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

**This is a successful experiment on one synthetic tool-using agent, not proof
of general agent-migration reliability.** Repeated trials, wider agent support,
a deployed Vultr app and sandbox isolation remain to be demonstrated.

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
agents; external-agent imports remain unsupported. Built-in refund and
deployment tools now have an **opt-in isolated Docker/gVisor execution path**
using one disposable worker per scenario. A separate path runs real
Vultr-model-generated migration diagnostic Python in another worker.
Live calls require explicit server flags and an operator token. Deployment
on the actual Vultr VM has not yet been verified.

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
Docker runner but still needs deployment proof on Vultr. No arbitrary
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
  Vultr proof and full-stack integration remain pending.

## Remaining work

1. Reproduce the measured improvement on multiple new seeds and paraphrased
   tasks; quantify run-to-run variance.
2. Build the minimal judge-facing workflow and Vultr-hosted control plane.
3. Verify gVisor containment and secret separation on the actual Vultr VM;
   the CI proof currently runs on GitHub-hosted machines.
4. Publish the reproducible demo, video and submission evidence.

This is the **Refit product repository**. The separate dev-mcp service is a
development tool, not part of the shipped product.

MIT licensed.
