# Refit

**Change the model. Keep the behavior.**

Refit finds and repairs tool-use regressions when migrating an AI agent to a
different language model. It compares actual stateful outcomes, proposes
bounded model-facing changes, and tests them against independent scenarios.

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

The accepted adaptation combined an **AI-generated instruction rewrite** with
an evidence-triggered runtime guard requiring the target model to call
`get_order` first. The independent SQLite gateway and verifier did not change.

**This is a successful experiment on one synthetic tool-using agent, not proof
of general agent-migration reliability.** Repeated trials, wider agent support,
a deployed Vultr app and sandbox isolation remain to be demonstrated.

## Code

- `scripts/refit_vultr_probe.py` — baseline 3-case Vultr migration experiment.
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
python3 -m scripts.refit_stress_probe \
  --source deepseek-v4.1-flash-1017 \
  --targets muse-glimmer-30b \
  --repair deepseek-v4.1-flash-1017 \
  --max-requests 160 \
  --output refit-stress-report.json
```

Vultr inference calls are billable. The report contains only synthetic
orders, model-generated instructions and traced tool calls. Refit checks that
the actual returned model matches the requested model.

## Trust and correctness

- The agent has only two declared tools: `get_order` and `issue_refund`.
- The gateway enforces identity, eligibility, exact minor-currency-unit
  refund amounts, and idempotency. It never touches real customer accounts.
- Model prose isn't the oracle: Refit checks the transaction database state,
  tool call sequence, authorized outcomes and fresh holdout cases.
- Repair candidates are bounded to instructions, tool descriptions and an
  evidence-triggered named first-tool policy. They cannot edit the evaluator.
- In-process SQLite tools are **not** arbitrary-code isolation; a separate
  hardened Vultr worker and containment test are still needed.

## Remaining work

1. Reproduce the measured improvement on multiple new seeds and paraphrased
   tasks; quantify run-to-run variance.
2. Build the minimal judge-facing workflow and Vultr-hosted control plane.
3. Demonstrate real sandbox containment and secret separation.
4. Publish the reproducible demo, video and submission evidence.

This is the **Refit product repository**. The separate dev-mcp service is a
development tool, not part of the shipped product.

MIT licensed.
