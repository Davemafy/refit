# Refit

**Move AI agents between models without silently breaking their tools.**

Refit is a working, test-first prototype for agent-model migration. It replays
business tasks against an existing agent and a candidate model, observes real
tool calls and state transitions, proposes bounded changes to the agent-facing
configuration, and accepts a candidate only after independent verification.

## Current evidence

- A live Vultr comparison of DeepSeek V4.1 Flash and GLM 5.2 completed:
  **source 3/3; candidate 3/3; no reproduced regression**. The result is not
  a successful automatic repair.
- 19/19 offline protocol tests passed in the original dev-mcp development branch.
- A stronger eight-scenario stress suite has been implemented. Its **live**
  results have not yet been verified.
- The prototype is not yet a publicly deployed Vultr application or a fully
  compliant hackathon submission.

We do not report a repair unless the target model actually fails a task that the
source model passes, a Vultr-hosted model generates a permitted change, and
protected validation and holdout cases show that the change works.

## Repo layout

- \`scripts/refit_vultr_probe.py\`: initial 3-scenario live migration experiment.
- \`scripts/refit_stress_probe.py\`: 8-scenario tool-behavior stress suite with
  transient lookup failures, user attempts to override authorization, misleading
  tool content and timeout-after-write checks.
- \`tests/\`: independent deterministic unit tests; no paid API calls.
- \`.github/workflows/ci.yml\`: reproducible offline tests on pull requests and pushes.

## Run the tests

Python 3.11+; no pip dependencies required:

\`\`\`bash
python3 -m unittest discover -s tests -p 'test_refit*.py' -v
\`\`\`

## Run the real experiment on Vultr

The inference API key must stay in a private server environment, not in the
repository, the browser, or CI logs. The experiment reads
\`VULTR_INFERENCE_API_KEY\` or a root-readable environment file such as
\`/etc/refit/inference.env\`.

\`\`\`bash
python3 -m scripts.refit_stress_probe \
  --source deepseek-v4.1-flash-1017 \
  --targets glm-5.2,muse-glimmer-30b,raon-1-mini-preview \
  --repair glm-5.3-flash \
  --max-requests 100 \
  --output refit-stress-report.json
\`\`\`

The command makes billable Vultr inference requests. The request count is
bounded by \`--max-requests\` (default 100). The response's model ID is checked
to reject an unexpected fallback.

The suite uses **synthetic** orders and an in-memory SQLite database; it does
not access or refund real customer orders.

## Security and limitations

- The candidate model can propose only instructions or tool descriptions.
  It cannot change business rules or the independent verifier.
- A refusal that prevents a required eligible refund is a task failure.
  An unauthorized refund attempt counts separately, even if a gateway blocks it.
- The verifier checks database state and tool traces, not the model's final
  prose. Holdout case IDs and amounts differ from training cases.
- Fixed, in-process SQLite tool calls are **not** a secure arbitrary-code
  sandbox. The Vultr-hosted containment demonstration remains to be built and
  independently tested.
- Arbitrary imported agents, production-grade migration, recovery, observability
  and product UI are not implemented yet.

## What comes next

1. Find a **genuine** model-induced regression on multiple realistic cases.
2. Produce and retest the minimal model-facing patch with Vultr inference.
3. Require clean protected holdout and security checks, across repeated trials.
4. Deploy the actual Refit controller and isolated workers on Vultr.
5. Publish a cold-start judge-accessible demo, real recordings and evidence.

The original development experiments are in
[dev-mcp PR #3](https://github.com/Davemafy/dev-mcp/pull/3).
This repository is the product home; dev-mcp stays a separate development tool.

## License

MIT.
