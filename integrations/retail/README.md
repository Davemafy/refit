# Original retail-agent migration

This adapter uses the independently developed retail agent in
[Sierra's tau2-bench](https://github.com/sierra-research/tau2-bench), pinned to
`033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`.

It imports the original retail database, tools, policy, customer scenarios,
`LLMAgent`, `UserSimulator`, `Orchestrator` and complete evaluator. No Refit
refund fixtures are used. This is an upstream customer-service simulation,
not a live commercial shop or a general repository importer.

## Run

Review the manifest and adapter first. Docker with registered gVisor `runsc`
is required. Build steps do not receive an inference key:

```bash
docker build -f integrations/retail/Dockerfile -t refit-original-retail .
python -m scripts.container_agent --manifest integrations/retail/manifest.json \
  --image refit-original-retail --output ./retail-inspect
```

Inspection makes zero inference calls. It checks the original checkout,
nonoverlapping task splits, schemas, policy and expected state changes.

For the live run, set `VULTR_INFERENCE_API_KEY` privately on the **host**:

```bash
python -m scripts.container_agent --manifest integrations/retail/manifest.json \
  --image refit-original-retail --output ./retail-live --execute
```

The declared cap is **400 total Vultr requests**, including both business
models, customer-simulator calls, repair generation and the final native-runner
verification. There are no automatic provider retries or billable job retries.
All imported Python runs inside a networkless, unprivileged, read-only gVisor
container. A bounded JSONL broker makes model requests on the host. The key,
host filesystem, Docker socket and public paid endpoints are never exposed to
the imported code.

The engine retains its original source, validation and untouched-holdout gates.
The original tau2 state and task evaluators determine outcomes. Tool errors
are additionally counted conservatively against acceptance. Task IDs are
predeclared in the manifest, with distinct train, validation and holdout sets.
The whole initial database is fingerprinted for every execution and compared
across models. Expected actions are used only by the evaluator, never placed
in agent or user prompts.

## Export and apply

A verified run emits `agent-config.json` and `apply_config.py`. An unchanged
replacement is explicitly `compatible_on_sample`; its export changes the
model configuration without pretending an instruction repair was needed.
A repaired migration includes the normal compatibility receipt as well.
An unsuccessful native-runner recheck withholds the export.

Copy both files into the pinned original developer checkout. Install its
normal dependencies and construct its original runner as usual:

```python
import json
from apply_config import agent_from_export
from tau2.domains.retail.environment import get_environment

environment = get_environment()
configuration = json.load(open("agent-config.json"))
agent = agent_from_export(environment, configuration)
# Pass this agent to the upstream tau2 Orchestrator with the original user/task.
```

The helper changes only the model-facing instruction text and optional tool
descriptions. It checks the baseline, protected policy, tool names and parameter
schemas before applying anything. Original tool functions, database and business
policy are unchanged. `ConfiguredAgent` subclasses `LLMAgent` solely to supply
configuration; conversation and tool execution use the original framework.
The integration reruns the complete original Orchestrator on holdout tasks
using this exact exported configuration before releasing it.

For tau2's own LiteLLM transport rather than Refit's credential-isolating
broker, configure the OpenAI-compatible provider explicitly in the original
trusted deployment:

```python
import os
agent.llm = "openai/" + configuration["model"]
agent.llm_args.update({
    "api_base": "https://api.vultrinference.com/v1",
    "api_key": os.environ["VULTR_INFERENCE_API_KEY"],
    "temperature": 0,
})
```

The provider prefix selects LiteLLM's transport; the served model remains the
one named in the export. Refit's verified execution keeps this credential on
the broker host instead of injecting it into imported agent code.

To verify an existing export through the complete original runner, without
another repair search:

```bash
python -m scripts.container_agent --manifest integrations/retail/manifest.json \
  --image refit-original-retail --output ./retail-export-check \
  --verify-export ./retail-live/agent-config.json --max-requests 64 --execute
```

This has its own explicit request cap and retains both success and failure
records. It does not reuse cached responses or automatically retry a failed run.

## Components considered

We reviewed [Promptfoo's custom evaluation providers](https://www.promptfoo.dev/docs/getting-started/)
and [Inspect's agent bridge](https://inspect.aisi.org.uk/agent-bridge.html), along
with the smaller Swarm shopping and Pydantic bank examples. This integration
reuses tau2's original conversational runner and state evaluator, and Refit's
existing migration gates. The added boundary handles isolated adapter loading,
bounded credential-free IPC, and host-side billing; it does not replace the
original agent or implement a new business evaluator.

## Reuse for another agent

The host protocol in `scripts/container_agent.py` does not import adapters.
A reviewed adapter is packaged in a dedicated image and implements:

- `describe(config) -> (AgentContract, AgentProfile, metadata)`.
- `cases(config, split) -> list[ReplayCase]`, with a native `runner` callable.
- `verify_export(client, config, exported) ->` measured original-runner cases.

Native runners return the existing engine result schema, including transcripts,
actual model request counts, independent verdicts and initial/final state
fingerprints. Customer-specific fixtures and outcome checks remain adapter
responsibilities. The first host release checks retail state metadata and ships
the retail deployment helper; another integration needs its corresponding
state binding and application helper. This is a reusable execution boundary
and runner contract, not automatic support for every framework.

The wire contract uses these concrete fields:

| Object | Required data |
| --- | --- |
| Description metadata | `upstream_revision`; `splits` mapping split names to rows |
| Each task row | `case_name`, input fingerprint, `initial_db_hash`, `expected_db_hash` |
| Native case result | `case`, `passed`, `verdict` with integer error counts, `error`, `trace`, `transcript`, `model_requests`, `elapsed_seconds`, `initial_db_hash`, `final_db_hash` |
| Export verification | `passed`, `uses_exported_configuration`, complete holdout `cases`, actual `model_requests` |

State hashes can describe another agent's business state; they need not come
from SQL. Call `client.record_case(result)` after each native case to preserve
completed evidence even if final delivery fails. The client exposes only
`complete(model, messages, tools)`, a request counter and that checkpoint method.
Set `application_helper` in the manifest to reviewed Python source under
`integrations/`; the host copies it into the export without importing it.

The image and adapter must be reviewed before trusting their oracle. Isolation
protects the host from imported code; it cannot establish that an arbitrary
customer-supplied evaluator tells the truth.

## Evidence and failure states

`run.json` records image identity, source revision, protected input fingerprints,
all completion attempts, measured engine stages, complete native transcripts,
final exported-runner checks and Docker cleanup proof. Provider failures,
budget exhaustion, source failures, rejected repairs and cleanup failures retain
the evidence and cannot publish a configuration as verified.

The optional GitHub workflow builds and inspects without inference on code
changes. Billing happens only when `experiments/external-agent-run.json` is
explicitly changed with `execute: true`. Subsequent code commits do not
automatically repeat that paid plan. Do not manually rerun a paid job without
reviewing its already-spent budget.
