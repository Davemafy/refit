# Engineering architecture

## Scope

Refit aims to migrate tool-using agents between model providers while preserving
authorized, stateful behavior. This prototype supports one fixed synthetic
customer-support agent and its two declared tools. It is not a universal agent importer.

## Execution flow

1. Load approved model IDs and the inference credential exclusively in the controller.
2. Execute source and candidate configurations on identical synthetic business scenarios.
3. Record actual tool calls (names, arguments, results) and check SQLite transaction state.
4. Identify cases the source passes but the candidate fails.
5. Ask a Vultr model to generate a bounded patch to instructions/tool descriptions.
6. Reject fields outside the allowed patch scope.
7. Re-execute training, independent validation and fresh holdout scenarios.
8. Export true results only. Never label ordinary model compatibility as a repair.

## Trust boundary

The tool gateway enforces order ownership, eligibility, amount and idempotency.
The model does not receive SQL access or modify evaluator assertions.
The current SQLite tools run in-process: this is useful for evaluator correctness
but **not** sufficient isolation for Blast Radius Zero. Hardened disposable
workers with network and resource confinement are still required on Vultr.

## Demo gates

- Source and target inference responses include verified requested model ID.
- Real source > candidate behavioral difference reproduced on repeated runs.
- Generated patch changes only permitted model-facing fields.
- Holdout improves after the patch; no regression in authorization safeguards.
- Containment and host integrity independently demonstrated on Vultr.
- Public browser demo and code evidence reproducible by judges.
