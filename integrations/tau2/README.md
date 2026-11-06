# τ-bench agent runner integration

Refit can apply its exported model configuration in the independently authored
τ-bench `LLMAgent`, pinned to upstream commit
`033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`.

This is a **framework integration**, not an independently verified production
customer deployment or a τ-bench leaderboard result. Refit's existing refund
fixtures and independent business oracle remain the evaluation environment.
Upstream source code is not edited or copied into Refit.

## Install and execute

Use Python 3.12 in a separate virtual environment:

```bash
python3.12 -m venv .venv-tau2
.venv-tau2/bin/pip install -r integrations/tau2/requirements.txt
git clone https://github.com/sierra-research/tau2-bench.git /tmp/refit-tau2-source
git -C /tmp/refit-tau2-source checkout 033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f
export TAU2_DATA_DIR=/tmp/refit-tau2-source/data
REFIT_TEST_TAU2=1 LITELLM_LOCAL_MODEL_COST_MAP=true \
  .venv-tau2/bin/python -m unittest tests.test_refit_tau2 -v
```

Preview the fixed-patch verification without model requests:

```bash
.venv-tau2/bin/python -m scripts.verify_frozen_patch \
  --runner tau2 --domain refund \
  --patch data/recorded/refund-compatibility-2026-11-06.artifact.json \
  --seeds 723001 723002 723003 --paraphrase --max-requests 400
```

Add `--execute` to make bounded live inference calls using the existing private
Vultr credential. The patch is frozen before these seeds are evaluated. No repair
model is used during this verification. All trials, including failed ones, remain
in the report. Separate fresh seeds still use known workflow families.

## Integration boundary

To run the complete detect, propose, verify and export loop through this runner:

```bash
.venv-tau2/bin/python -m scripts.refit_cli --runner tau2 --domain refund \
  --source deepseek-v4.1-flash-1017 --target muse-glimmer-30b \
  --max-requests 400 --output refit-migration-report.json \
  --export-patch refit-compatibility.json
```

This command makes real inference calls. A compatible target requires no patch;
a failing target receives a patch only if independent gates verify improvement.

`Tau2Client` registers tools with upstream `LLMAgent`, converts the conversation
into upstream typed messages, and calls the original `generate_next_message`.
The exported instructions populate its system configuration. A locked provider
seam forwards generation to Refit's budgeted Vultr client. The seam is restored
on success or exception. The original upstream agent updates its own state and
produces tool calls; Refit's resettable gateway executes them and independently
verifies resulting business state.

This bridge is process-local and serializes its provider seam. The upstream
runner and its dependencies are trusted host code, not sandboxed uploads. Tool
executors stay separate from model transport. No production side effects are
performed by the included evaluation fixtures.
