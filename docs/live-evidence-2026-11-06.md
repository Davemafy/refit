# First verified real-model repair — November 6, 2026

## Result

**Status: `verified_repair`** in [GitHub Actions run #42193722623](https://github.com/Davemafy/refit/actions/runs/42193722623).
The workflow executed the actual Vultr Serverless Inference endpoint and
checked that returned model identifiers matched the requested models.

- Source: `deepseek-v4.1-flash-1017`
- Migrated target: `muse-glimmer-30b`
- Repair proposer: `deepseek-v4.1-flash-1017`
- Total inference calls: **129**
- Baseline source training: **8/8**
- Migrated target before repair, training: **5/8**
- Target after repair, training: **8/8**
- Independent validation: **8/8**
- Unmodified target on protected holdout: **7/8**
- Repaired target on the same holdout: **8/8**
- Unsafe refund attempts on all reported evaluation gates: **0**

Full synthetic replay evidence is archived temporarily as the
`refit-synthetic-live-report` artifact attached to run #42193722623
(GitHub Actions artifacts are time-limited).

## What actually changed

Refit first observed that Muse skipped required order lookups, including
the `eligible`, `skip_lookup`, and `timeout_after_commit` training scenarios.

An actual Vultr inference model proposed a bounded rewrite of the agent's
instructions. Refit then selected the **`instructions_with_lookup_guard`**
variant. The guard sets the first model tool choice to the named
`get_order` function when training traces show mandatory lookup was skipped;
subsequent tool calls use normal model selection. The model continues to
execute `get_order` through the audited gateway; Refit does not fabricate a
refund tool result.

The independent SQLite gateway still enforces ownership, eligibility,
minor-currency-unit accuracy and idempotency. The verifier and task assertions
were not edited to accommodate the new model.

## Historical attempts (not successful repairs)

| Trial | Observed result |
| --- | --- |
| [#42191002488](https://github.com/Davemafy/refit/actions/runs/42191002488) | DeepSeek 8/8; GLM 5.2 8/8, no regression |
| [#42191228870](https://github.com/Davemafy/refit/actions/runs/42191228870) | Muse 6/8; repair generation failed |
| [#42191791905](https://github.com/Davemafy/refit/actions/runs/42191791905) | Muse 5/8; generated full patch fell to 2/8; rejected |
| [#42192333449](https://github.com/Davemafy/refit/actions/runs/42192333449) | Selective instruction patch reached 7/8; rejected |
| [#42192866064](https://github.com/Davemafy/refit/actions/runs/42192866064) | Instruction patch 8/8 training but 7/8 validation; rejected |
| [#42193722623](https://github.com/Davemafy/refit/actions/runs/42193722623) | Model-generated instructions + bounded lookup guard passed 8/8 on training, validation and holdout |

## Limits of this claim

This result demonstrates a **successful, measured migration of one synthetic
order-refund agent between two actual Vultr-hosted language models**. It is
not yet evidence of reliability across arbitrary imported agents, broader
industries, unseen task families or multiple stochastic repetitions.

The source and target were evaluated on fixed task families with independently
randomized synthetic order IDs, amounts, owners and state for each phase.
The holdout cases were not supplied to the repair proposer.

The evaluator runs on GitHub-hosted Actions; model inference is provided by
Vultr. The hackathon still needs a deployed Vultr-hosted Refit control plane,
reproducible reviewer demo, and real isolated worker containment evidence.
Neither Docker isolation nor public user-facing deployment has been established
by this benchmark.
