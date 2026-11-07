# mini-SWE-agent migration

This integration runs the original `DefaultAgent`, `LitellmModel` action parser,
and `LocalEnvironment` from mini-SWE-agent 2.4.6, pinned to
`04d809ceab9df28f9adaed044884180159172930`. Only the provider transport is
redirected to Refit's existing Vultr broker. The original bash tool schema,
agent loop, observations, task prompt and submission protocol are preserved.

The genuine task is [Requests issue #2316](https://github.com/psf/requests/issues/2316),
at unfixed revision `091991be0da19de9108dbe5e3752917fea3d7fdc`.
Byte-valued HTTP methods become strings such as `B'GET'`. Protected, offline
Python tests inspect the method prepared by the real Requests code before
network transmission. They cover byte methods and ordinary string methods.
The upstream fix from PR #2317 is used only for a zero-inference red/green
preflight, outside the agent image and live model context.

## Reproduce through the isolated original runner

From the Refit checkout, with Docker's `runsc` runtime installed:

```bash
docker build -f integrations/mini_swe/Dockerfile -t refit-mini-swe .
python -m integrations.mini_swe.run --image refit-mini-swe --output ./mini-inspect \
  --reference-patch experiments/mini-swe-reference.patch
```

Inspection makes no inference requests. For a new, explicitly billable run,
privately configure `VULTR_INFERENCE_API_KEY` on the broker host, then:

```bash
python -m integrations.mini_swe.run --image refit-mini-swe --output ./mini-live --execute
```

The cap is **61 total inference requests**, including source, replacement,
any bounded instruction repair and fresh export verification. Each native
agent has a 12-step limit. The broker does not retry provider failures.
The committed Actions plan is disabled after the recorded run; changes to
adapter code alone cannot trigger a paid run.

Imported code executes only in the existing read-only, networkless gVisor
container, with an unprivileged user and temporary task checkouts. The key
stays outside that container. Source and replacement solve clean copies of
the same task. The exported target configuration then gets one **fresh**
original-agent execution on another clean copy.

Validation and holdout apply each agent's frozen code diff to a clean checkout
in a separate, networkless gVisor container. The broker supplies fixture inputs
only to that disposable evaluator over stdin. The agent image contains the
training example and no held-out fixtures or reference patch. The generation
worker receives only the evaluator verdict and receipt number. The host binds
the receipt to the diff and retains the full checks and cleanup in `run.json`.
These partitions test one issue. Failure of any required gate withholds the export.

## Use the export

A verified run produces ordinary `agent-config.yaml`, the integrity-checked
`agent-config.json`, and `apply_config.py`. The YAML has no Refit dependency
and no credential. It selects Vultr's OpenAI-compatible endpoint and the
replacement model while preserving mini-SWE-agent's original templates.
To reconstruct the YAML, inside the pinned original agent installation:

```bash
python apply_config.py agent-config.json agent-config.yaml
```

For a trusted developer-owned checkout, the original API can load the YAML:

```python
import yaml
from minisweagent.agents import get_agent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models import get_model

config = yaml.safe_load(open("agent-config.yaml"))
# Configure credentials privately in your trusted deployment's provider.
model = get_model(config=config["model"])
agent = get_agent(model, LocalEnvironment(cwd="/path/to/your/task"), config["agent"])
result = agent.run("Your coding issue")
```

For imported/unreviewed code, use the isolated broker command above rather
than passing credentials into the agent environment. Its exported YAML is
loaded by the same original model/agent factories for the fresh acceptance
run. `sitecustomize.py` supplies removed `collections` aliases so this old
Requests checkout runs on Python 3.11; it does not change the issue's source.

## Supported scope

This is one reviewed mini-SWE-agent adapter and one genuine coding issue.
It establishes a working model-configuration export, not compatibility with
all coding tasks or arbitrary repositories. No regression is invented if
both models solve the issue. In that case the engine reports
`compatible_on_sample` and exports a model-only configuration.

For the next reviewed coding repository, the existing adapter contract,
container runner, broker, migration gates and export path are reusable.
Supply a pinned task checkout, issue text and protected executable outcome
tests; replace this adapter's task-specific checkout/oracle binding. There is
no automatic repository importer. Tool schema or implementation repairs are
outside this adapter's scope; bounded system-template changes use the existing
repair engine.

## Recorded result — migration rejected

The [single live run](https://github.com/Davemafy/refit/actions/runs/42325474336)
executed commit `3cd13cc5709ae9bae1555da48540d0167dff9e36` using actual Vultr
inference. It spent **35 of 96 requests**: source 10, replacement 12,
repair proposal 1, instruction-repair trial 12. There were no provider retries
or repeated paid runs.

- DeepSeek: protected training test passed; original runner returned `Submitted`.
- GLM: its actual code change passed the same test, but it exhausted 12 steps
  trying optional legacy tests and installing unavailable pytest instead of
  submitting. Its original runner returned `LimitsExceeded`.
- Existing bounded repair: generated completion-protocol instructions, then
  GLM exhausted 12 steps without a tracked source change. Training rejected it.

The engine reported `repair_rejected_training`. Validation/holdout and fresh
export acceptance were **not reached**. No model configuration is released as
verified, and no successful migration is claimed. The trial's
`unsafe_attempts: 1` reflects the adapter's failed allowed-change gate (no
tracked change), not a detected host escape. Its immutable cleanup receipt
confirms removal and healthy Docker after the `runsc` container exited normally.

This first run established a completion failure within the original 12-step
limit. Its verifier lived in the generation container, so its evaluation
partitions did not have the isolation of the current runner.

The original compressed report is `data/evaluations/mini-swe-requests-2316-001.json.gz`.
The preflight report sits alongside it. `evidence/source.patch` and
`evidence/replacement.patch` are diagnostic copies of actual model changes,
**not accepted compatibility artifacts**. The empty repair-trial patch records
that no tracked source change was produced. Existing refund/retail artifacts
and the public deployment were not changed.

Original report SHA-256: `b778365cdea71798c015522af519b1a01ceeb565b8b172dd961bca8f6b28a7d4`.

## Isolated follow-up on November 7, 2026

The [paid follow-up](https://github.com/Davemafy/refit/actions/runs/42347731383)
ran at commit `292c7d5508100ff1b0ab9847f454938229155d12`. Its zero-inference
preflight reproduced the issue and verified the upstream fix in separate
evaluator containers. The source and unmodified target each submitted a
patch in 12 model requests. Each frozen patch passed training, validation,
and holdout. The engine reached `compatible_on_sample` without generating a
repair because the target passed training.

The final export gate reran the original target agent from a clean checkout
with the proposed export loaded. Its new diff passed all four holdout
assertions, but the agent attempted to run pytest after the training verifier
passed and exited with `LimitsExceeded` before submitting. The final status
was `export_failed_original_runner_verification`, and the export was withheld.
The observed failure is intermittent under the original 12-step limit.

The follow-up used 36 of its 61 allowed requests. Across both paid runs the
total was 71 of the original 96. All seven live evaluator containers and the
generation container had verified cleanup. Full model traces, diffs and
patch-bound receipts are preserved in
`data/evaluations/mini-swe-requests-2316-002.json.gz`. The six red/green
preflight receipts are in `data/evaluations/mini-swe-requests-2316-002-preflight.json.gz`.

Original follow-up report SHA-256: `f15223cae5956f75b8e7d6521bb595da62c94a12f8a102a52867e0f1c27c6e66`.
