# Refit shared-engine evidence — November 6, 2026

## What we can substantiate

One general **contract-driven migration engine** now evaluates two separate
tool-using agents, with different tools, side effects, business contracts and
independent state verifiers:

- **Customer refunds**: \`get_order\`, \`issue_refund\`; ownership, eligibility,
  exact minor-unit amounts, idempotency and timeout-after-commit recovery.
- **Deployment incidents**: \`inspect_service\`,
  \`inspect_recent_deploy\`, \`rollback_release\`, \`verify_service\`;
  authorization, active/previous releases, idempotent rollback and verified
  service recovery.

Both use \`scripts/migration_engine.py\`. Domain-specific actions live behind
independent adapters and independent outcome oracles.

### Real-model repair, through the generic engine

[GitHub Actions run #42207396750](https://github.com/Davemafy/refit/actions/runs/42207396750)

| Evaluation phase | Result |
| --- | --- |
| Original DeepSeek source | 8/8 training |
| Unmodified Muse target | 6/8 training |
| Adapted Muse target | **8/8 training** |
| Independent validation | **8/8** |
| Unmodified Muse target on holdout | 7/8 |
| Adapted Muse target on holdout | **8/8** |
| Unsafe attempts | **0** |
| Real Vultr inference requests | 134 |
| Decision | \`verified_adaptation\` |

The generic engine generated and selected a pure
\`instructions_only\` change. The accepted rewrite requires an authoritative
lookup even for ineligible orders and verification of state after ambiguous
post-commit timeouts. It does **not** change the independent refund gateway or
the protected verifier. This result is separate from the earlier
refund-specific repair implementation.

The original report and synthetic traces are retained in the short-lived
GitHub Actions artifact attached to this run.

### Real-model cross-domain compatibility

[GitHub Actions run #42205523011](https://github.com/Davemafy/refit/actions/runs/42205523011)
evaluated DeepSeek → Muse on the independent deployment agent: source 8/8,
target 8/8, zero unsafe attempts, 63 inference requests. The migration was
correctly reported as compatible without repair *on the training sample*.

[GitHub Actions run #42206326304](https://github.com/Davemafy/refit/actions/runs/42206326304)
evaluated DeepSeek → Raon after adding independent validation of unchanged
targets:

| Evaluation phase | Result |
| --- | --- |
| DeepSeek source | 8/8 training |
| Raon target | **8/8 training** |
| Raon independent validation | **8/8** |
| Raon independent holdout | **8/8** |
| Unsafe rollback attempts | **0** |
| Recoverable read-only errors in source training | 1 |
| Real Vultr inference requests | 126 |
| Decision | \`compatible_on_sample\` |

A pass does not mean an agent has been repaired or that it will succeed on
every future task. Refit does not invent failures or mutate protected policies
to create a demonstration.

## Important failure of our own harness — corrected

In the first deployment-domain run, the original model passed only 3/8 and
was reported as attempting unsafe rollbacks. Inspection of the *actual*
tool traces showed our simulator had a contract bug:

- \`inspect_recent_deploy\` correctly returned \`previous_release\` as the
  rollback target.
- The model correctly passed that previous release as \`release_id\`.
- The gateway **incorrectly expected the active release**, falsely rejecting
  valid rollback attempts.

We repaired the tool contract and added regression tests. Another test revealed
a read-only inspection call made too early during recovery from a transient
health API error; it was rejected safely and the model still completed
the authorized rollback. We now record **recoverable errors** separately
from unsafe actions and actual outcome failures.

These changes increased source-model success to 8/8 on this sample without
weakening the protected rules. This is why Refit must verify not only model
behavior but the integrity of the *evaluator itself*.

Earlier incorrect failure runs remain available as transparent historical
evidence, not as evidence of unsafe model behavior.

## Machine-readable user-facing integration

The common CLI is:

\`\`\`sh
python3 -m scripts.refit_cli \
  --domain refund \
  --source deepseek-v4.1-flash-1017 \
  --target muse-glimmer-30b \
  --repair deepseek-v4.1-flash-1017 \
  --max-requests 160 \
  --output refit-migration-report.json \
  --export-patch refit-compatibility.json
\`\`\`

Choose \`--domain deployment\` for the second supported agent.

A locally trusted adapter may also be imported with \`--adapter module.path\`
if it exports \`CONTRACT\`, \`BASE_PROFILE\` and \`run_live\`.
**Never allow arbitrary uploaded adapters to execute on a public server**;
Python imports execute code and currently require a controlled trusted
environment.

The CLI exports \`refit-compatibility.json\` only after a verified adaptation.
Its reviewable JSON includes:

- patch and model identities;
- the original tool/contract fingerprint and original configuration fingerprint;
- the accepted target-facing instructions and tool descriptions;
- training, validation and holdout outcome receipts;
- an integrity digest, which detects accidental edits but **is not a
  cryptographic signature**.

\`scripts/compatibility_artifact.py\` rejects a patch if the target model,
approved business contract or original configuration differs. No production
agent is silently switched or rolled back.

## Verified export from the real live result

[Offline GitHub Actions export run #42208894380](https://github.com/Davemafy/refit/actions/runs/42208894380)
retrieved the archived *actual* live refund migration report from run
#42207396750 and used `create_receipt` followed by `validate_and_load`
to generate and check a versioned compatibility artifact.

- Artifact format: `refit.compatibility.v1`
- Contract: `conditional_customer_refunds`
- Source: `deepseek-v4.1-flash-1017`
- Target: `muse-glimmer-30b`
- Accepted adaptation type: `instructions_only`
- Integrity checksum:
  `sha256:19cb9d6f15d45dd114ff384e00b0324d5506f74dcf83276f17033e2bc8f1943b`
- New inference calls for export: **0**

The artifact contains target instructions, the approved protected-contract
fingerprint, the original configuration fingerprint and measured evaluation
scores. It contains no API key or executable program.

A checksum is not proof of authorship. Developers must still review changes
and explicitly integrate/roll out the configuration. The JSON represents
a **verified configuration proposal**, not an automatically updated live
customer agent.

## Remaining proof obligations

1. Support an actual external agent framework adapter, not only built-in
   synthetic environments.
2. Have developers approve their business invariants and replay fixtures;
   source-model traces are evidence, not ground truth.
3. Measure behavior across repeated stochastic trials, new task families,
   distinct tool shapes, latency, cost and operational limits.
4. Run the control plane and disposable worker on **Vultr compute**, and
   independently demonstrate sandbox containment. GitHub-hosted CI with
   Vultr inference is not a substitute for a Vultr-hosted application.
5. Build the judge-accessible demo and provide a safe patch review/apply
   workflow with explicit authorization and rollback support.

The results show a successful **narrow generalization of the engine
architecture across two agent domains**, with one actual generated repair.
They do *not* establish the general ability to repair arbitrary imported
agents or a reliable population success rate.
