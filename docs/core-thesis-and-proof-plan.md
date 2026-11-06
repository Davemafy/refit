# Refit's core thesis: operational compatibility, not prompt similarity

**Research and architecture decision — November 6, 2026**

## The problem, precisely

Changing an AI agent's underlying language model can change whether the agent
calls a tool, which tool it calls, the arguments, call ordering, retries,
conversational decisions, and the final business-state transitions.

**The user's contract is not "same text" or "same trajectory".** It is:
given a task and an initial state, the migrated agent should reach an allowed
outcome, obey forbidden-action constraints, satisfy required workflow steps, and
stay within operational budgets. Multiple different tool trajectories can
legitimately produce the same outcome.

Refit's testable claim:

> Given a supported tool-using agent, a target model, executable replay
> scenarios, and independently defined business/safety invariants, Refit
> detects model-induced incompatibilities, produces bounded model-facing or
> runtime adaptations, and verifies them on untouched stateful cases. It can
> refuse migration when it cannot establish acceptable behavior.

This is **observational compatibility over a declared task distribution**,
not exact equivalence of two arbitrary stochastic programs. No honest product
can guarantee all possible future agent behavior from a finite suite.

### The indispensable prerequisite: an oracle

A source model's output is NOT automatically ground truth. A trace might show
a successful-looking answer while a real refund never happened; the source
might itself do unsafe things. Refit needs independent outcome assertions,
authorization invariants and a resettable side-effect environment.

A trace recorder can infer candidate contracts and propose tests, but any
critical rule inferred from business code needs human approval. Without
replayable state or an approved oracle, Refit may produce a compatibility
analysis, **not a verified migration**.

## Analysis of our actual evidence

See [the real Vultr run](https://github.com/Davemafy/refit/actions/runs/42193722623)
and [the archived methodology](live-evidence-2026-11-06.md).

- DeepSeek source: 8/8 training.
- Muse target: 5/8 training; sometimes stopped without calling \`get_order\`.
- Vultr-generated instruction change plus a **pre-implemented,
  evidence-triggered** first-tool selection policy: 8/8 training, 8/8
  validation, 8/8 holdout. Unmodified target: 7/8 on that holdout.
- No reported unsafe refund attempts. This is a true measured
  improvement on the tested agent and scenarios.

**Limits:** only one agent/domain, eight task templates, one accepted trial.
Repeated engineering experiments reused the same templates and test seeds.
New IDs and amounts did not make the task families unseen; the developer
observed some prior holdout failure categories. Thus the successful
holdout is **not a pristine once-only blind test**. Do not market 8/8 as a
general reliability percentage, and do not call the runtime tool guard an
algorithm spontaneously invented by the LLM.

Our archived synthetic report contains patch text, phase scores and failure
trace snippets. It does not retain every successful tool transition; future
reports must contain a richer independently replayable receipt.

## Architecture: seven separable jobs

### 1. Connect/capture

Accept one supported agent interface first. Reuse real framework integration
and standardized tool-call transport rather than trying to understand any
arbitrary repository. Capture sanitized prompts, model configuration, tool
schemas, tool-call events, durations, error statuses and side-effect IDs.

For v0, the entry contract is a small callable agent with explicit tools and
a resettable database. Next adapter: one popular agent framework. The product
must expose what it does NOT support.

### 2. Define protected behavior

The customer approves a *migration contract*:

- valid outcome assertions on business state and side effects;
- required preconditions (e.g. confirm ownership before refund);
- forbidden actions (unauthorized, duplicate, unsafe);
- domain-specific allowable tool-order variations;
- operational budgets (latency, cost, number of calls, side effects);
- replay fixture / sandbox reset instructions and data-privacy constraints.

The verifier, protected rule files, and fixture setup are **not writable by
the optimizer**. Any unapproved contract inferred by a model is provisional.

### 3. Replay and diagnose

Run the unchanged agent on both source and target against equal task/initial
state conditions, using actual model IDs. Measure *outcome* and trace-level
discrepancies separately.

Classify failure into:
- transport / provider API incompatibility;
- tool schema or argument-format incompatibility;
- incorrect tool selection / skipped prerequisite;
- multi-step plan, state tracking, or error-recovery failure;
- refusals / finalization before completing authorized work;
- safety / trust-boundary regression;
- irreducible capability or context limitation.

Attribution must be trace- and evidence-backed, not a speculative model
explanation. Where possible run a targeted counterfactual (such as force
the required tool, with business state and prompt held constant).

### 4. Generate a small, typed compatibility patch

Prefer deterministic proven transformations before expensive LLM search:
- provider argument/header normalization;
- strict schema or typed response validation;
- adapter mapping only if type-safe and semantics-preserving;
- required named tool only when a protected task precondition entails it;
- bounded retries, recovery state checks and idempotency handling;
- target-specific tool descriptions and instructions (GEPA-style feedback
  optimization can propose these, but independent evaluation is mandatory).

Each patch has:
- a machine-readable type and applicability condition;
- a minimal diff;
- the precise observed failure and why the proposed transformation should
  address it;
- a static proof that no protected policy/validator/fixture was changed;
- a declared performance/cost impact;
- an export path usable by the customer's agent.

**No arbitrary repository edits, unknown money conversion, invented
idempotency keys or model-written authorization changes.** If a model lacks a
required native capability and no safe adapter exists, block the migration.

### 5. Candidate search (bounded)

Test variants against *training* tasks only. Include the untouched baseline
and one-change-at-a-time variants. Use the observed training failures to
propose a small next mutation (e.g. instructions, tool schema, forced
prerequisite, retry policy). Record unsuccessful proposals; do not erase them.

Keep a small Pareto set for correctness, safety, cost and latency; don't
optimize one at the silent expense of the others. Stop by budget, not by
wishful thinking. Only deployable patch types can be selected.

### 6. Validate independently

Promotion requires:
- frozen task contract & verifier;
- repeated trials on distinct fresh states and paraphrased requests;
- at least one **new task family/domain** not used during repair search;
- a once-only blind validation split, generated after the candidate is frozen;
- no dangerous attempted actions, not merely absence of dangerous side effects;
- actual target improvement on paired scenarios, and no required regression
  relative to source; measure source failures too;
- cost and latency compared at equal workloads;
- capability and framework version IDs frozen into the receipt.

If confidence is low, report *insufficient evidence* even if the best single
run passed 8/8. Stop calling previously inspected holdouts "hidden."

### 7. Package, deploy and monitor

Export a versioned adapter (prompt/config/typed runtime rule), checksums,
environment and model IDs, before/after traces, verifier version, observed
success/failure rates and a reproducible evaluation command.

Outcomes:
- \`compatible_without_patch\`;
- \`verified_adaptation\` (within stated scope and empirical confidence);
- \`blocked\` with actionable evidence;
- \`needs_manual_review\` if the oracle or integration is incomplete.

Optional customer-controlled rollout uses shadow/canary, monitoring and
rollback; the product must not silently switch live agents.

## A concrete second-domain falsification

The *next* core test should not be another refund variant. Build a disposable
**deployment-incident agent** with different tools:

1. \`inspect_service\` — authoritative health and version;
2. \`inspect_recent_deploy\` — identify the suspected regression;
3. \`rollback_release\` — destructive but idempotent, only after checks and
   declared rollback authorization;
4. \`verify_service\` — confirm the real health state after rollback.

Cases: healthy service (no rollback), wrong application, missing approval,
transient health check error, timeout after rollback commit, malicious
diagnostic log instructing the agent to skip checks, duplicate rollback,
and a valid failing deployment.

The verifier checks actual version and health state, authorized change ID,
no duplicate rollback and mandatory verification. A model that merely
declares "rolled back successfully" fails.

This is a different set of business actions and recovery semantics. It is
also naturally relevant to Vultr's sandboxed-agent track. Run the whole
application against throwaway Docker fixtures, never production VMs.

**Falsification rule:** if our repair mechanism only works on the refund
agent, we have proven a domain-specific guard, NOT a reusable migration engine.
If a second domain requires a new hand-coded special case, document this
openly rather than presenting it as autonomous generalization.

## Hard requirement to resolve the existing evidence gap

Replace the current reused eight-template split with:
- training scenarios and explicit user-approved policies;
- a different, genuinely withheld combination of intents/tools/states;
- separate once-only holdout generated from a concealed seed at final test
  time, then permanently retired for subsequent revisions;
- repeated trials with empirical variability measured;
- run receipts preserving verified successful tool actions, not just scores;
- test harness version, environment snapshots and patch checksums.

Even a perfect 8/8 on one run cannot support a broad deployment reliability
claim. Non-deterministic agents must be evaluated across independent trials.

## Competition delivery boundary

For the Vultr submission, demonstrate a real narrow vertical slice:

Import a supported agent → switch to Vultr-hosted model → reproduce a
model-induced operational failure → Refit proposes an actual typed patch →
the same stateful task works on fresh evidence → export a reviewable
compatibility artifact → run the agent/tool execution in a separately
validated Vultr sandbox.

Keep the **control plane and disposable tools on Vultr**, use Serverless
Inference for the relevant model calls, and do not confuse GitHub Actions
tests with a Vultr-hosted application. CI is a development aid.

The primary demo need not claim universal autonomy. The winning bar is
credible real execution, an original and generalizable architecture, honest
limits, excellent evidence, and a clear customer benefit.

## Competitive position and reusable research

- [Microsoft Foundry migration guidance](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/model-migration):
  Discover → Assess → Adapt → Validate → Roll out → Retire; highlights
  that agent migrations require tools, schemas and calling-code changes.
  This is validation that the problem is real, and warns us that the
  lifecycle alone is not a unique product differentiator.
- [EvalShift](https://www.evalshift.dev/): existing trace capture, source/target
  replay, scoring, latency/cost comparison. Refit cannot claim to have
  invented model-migration testing.
- [BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html): tool selection,
  multi-turn actions and abstention are distinct from a text-only eval.
- [τ-bench](https://github.com/sierra-research/tau2-bench): tool-backed
  simulated real-world tasks, policy compliance, database-state outcomes,
  dynamic user actions and compositional task generation.
- [DSPy GEPA](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/GEPA/overview.md):
  trace-informed reflective instructions optimization. Reuse ideas for
  patch search; don't confuse optimizer scores with business truth.
- [PydanticAI tool retries](https://pydantic.dev/docs/ai/core-concepts/retries/):
  mature retry and validator mechanisms we can adapt instead of rebuilding.
- [Anthropic on non-deterministic evals](https://www.anthropic.com/research/demystifying-evals-for-ai-agents):
  pass@k vs pass^k, repeated trials and reliability over lucky single runs.

## The most important product decision

Ship a **verified, reversible compatibility patch** for supported agent
tool workflows—not a promise to preserve arbitrary model behavior forever.

The model may reason differently and produce different text. We preserve
the application's authorized, observable outcomes over a declared set of
tasks at a measured confidence level. When evidence is insufficient, say so.
