# Post-hoc causal ablation: instruction patch versus tool-choice guard

**November 6, 2026.** Two live Vultr Serverless Inference experiments, using the
same eight known *task templates* and different randomized order IDs, customer
IDs, amounts and states. This is an ablation of a previously selected repair,
**not an independent blind test of generalization**.

## Method

The candidate model was \`muse-glimmer-30b\`. The fixed repaired instruction
text was taken from the earlier real Vultr model-generated patch in [run
#42193722623](https://github.com/Davemafy/refit/actions/runs/42193722623).
Four conditions were evaluated against paired synthetic SQLite scenarios:

1. **Baseline**: original prompt and automatic tool selection.
2. **Guard only**: original prompt and requested first \`get_order\` tool call.
3. **Instructions only**: Vultr-generated instruction rewrite with automatic
   tool selection.
4. **Combined**: revised instructions plus requested first \`get_order\` call.

Each condition got its own resettable database for the same eight synthetic
cases; the verifier checked actual state and attempted unsafe operations.

## Results

| Condition | Seed 93670335 (83 API calls in run) | Seed 136807583 (81 calls in run) |
| --- | ---: | ---: |
| Baseline | 6/8 | 6/8 |
| Guard alone | 5/8 | 5/8 |
| Generated instructions alone | **8/8** | **8/8** |
| Instructions + guard | **8/8** | **8/8** |
| Unsafe refund attempts (all conditions) | 0 | 0 |

- [First full live run](https://github.com/Davemafy/refit/actions/runs/42196501466)
- [Independent-seed repeat](https://github.com/Davemafy/refit/actions/runs/42197001725)

Both full synthetic replay reports are retained as short-lived workflow artifacts.

### What the traces show

In the guard-only condition, Muse sometimes returned a final response without
a tool call **despite the request for named \`tool_choice=get_order\`**.
Therefore our Python flag called \`force_initial_lookup\` does NOT establish
enforcement at the model API boundary. Actual tool calls must be observed,
validated, and the task must fail closed if a required step is absent.

In both runs the guard-only case failed on \`timeout_after_commit\` and
\`poisoned_note\`; it also failed one no-lookup case. The new instructions
addressed stale state/timeout recovery and prompt injection in the order note,
and passed all eight cases without requiring the tool-choice hint.

### Interpretation

The two runs support a **narrow causal contribution**: the model-generated
instruction change was sufficient to repair the eight tested refund workflows;
the named-tool request alone was not. This changes the previous tentative
assumption that the deterministic tool-choice adapter may have carried the
success.

It does NOT prove:
- the same patch will consistently pass many independent stochastic runs;
- behavior on different task families or imported agents;
- that every model or provider honors \`tool_choice\`;
- that the instruction is a generally safe substitute for a runtime policy;
- that a finite test suite establishes universal behavior preservation.

The previous acceptance run used the **combined** patch. These post-hoc
ablations should be presented as additional diagnostic evidence, not as a
redefinition of what was deployed in that initial experiment.

## Consequences for the product

**1. Keep prompt optimization:** a model-generated rewrite has produced
measured behavioral improvement on real model inference.

**2. Make runtime guards genuine enforcement, not a request hint:** the
controller must check preconditions and actual tool results, and either
retry under a bounded policy, request human approval, or stop the operation.
It must never pretend a missing \`get_order\` happened.

**3. Stop reusing the refund suite as proof of generality:** the next critical
test is an independently authored **deployment-incident** or other
non-refund agent with different side effects, constraints and tools.

**4. Report stability and distribution:** record repeated trials across fresh
tasks, prompts, model responses, actual API cost and latency, and a genuinely
withheld once-only holdout. Stop relying on a perfect 8/8 as a reliability
claim.

The product target remains **verified compatibility for declared tasks and
invariants**, not identical textual outputs or guaranteed equivalence
between arbitrary language models.
