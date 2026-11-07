# Refit developer MVP

Run an agent against a replacement model, inspect real outcome regressions,
generate a bounded configuration adaptation, verify it independently, and
export a model-specific configuration receipt.

The [live framework verification](framework-evidence-2026-11-06.md) tested an
existing exported patch on three fresh seeds through the original external
tau2 runner: source 24/24, unchanged target 13/24, patched target 24/24, zero
unsafe attempts. The [public evidence preview](http://80.240.30.92) also passed
an independent nine-route check. Public paid actions are disabled; live
migrations run through the trusted CLI.

## Start

Use Python 3.11 or 3.12. The native runner has no third-party dependencies.

```bash
git clone https://github.com/Davemafy/refit.git
cd refit
python3 -m unittest discover -s tests -p 'test_refit*.py' -q
```

Set `VULTR_INFERENCE_API_KEY` privately in the process environment, or use the
existing root-readable `/etc/refit/inference.env` file. Then run:

```bash
python3 -m scripts.refit_cli \
  --domain refund \
  --source deepseek-v4.1-flash-1017 \
  --target muse-glimmer-30b \
  --repair deepseek-v4.1-flash-1017 \
  --max-requests 400 \
  --output refit-migration-report.json \
  --export-patch refit-compatibility.json
```

This command makes billable model calls within one hard request cap. Use
`--domain deployment` for the deployment-recovery workflow. A clean replacement
returns `compatible_on_sample` and needs no patch. A verified adaptation exports
the receipt; failed verification cannot export it. Reports retain measured
source, baseline target and candidate outcomes with their execution transcripts.

## Apply the configuration

The originating agent runner must apply the exact target instructions and tool
descriptions. Validate the receipt against its contract and baseline first:

```python
import json
from scripts import refund_adapter
from scripts.compatibility_artifact import validate_and_load

receipt = json.load(open("refit-compatibility.json"))
profile = validate_and_load(
    receipt,
    refund_adapter.CONTRACT,
    refund_adapter.BASE_PROFILE,
    "muse-glimmer-30b",
)
# Supply profile.instructions and contract.schemas(profile) to your agent.
```

The loader rejects a different model, changed protected contract, changed
baseline configuration or altered receipt. Its digest detects changes and is
not an authenticity signature.

## Verify an exported patch independently

Choose seeds before examining results. Preview without making requests:

```bash
python3 -m scripts.verify_frozen_patch --domain refund \
  --patch refit-compatibility.json --seeds 723001 723002 723003 \
  --paraphrase --max-requests 400
```

Add `--execute` for live verification. This command never generates another
repair. A shared request cap covers source, unchanged target and patched target
across all declared trials. Failure and budget exhaustion remain explicit.
Fresh seeds and request wrapping do not imply unseen workflow-family coverage.

## Connect an existing agent runtime

For the independently developed agent's **own business workflow**, use the
[original retail integration](../integrations/retail/README.md), not the older
runner-only bridge below. It executes the upstream retail policy, database,
tools, customer scenarios and full Orchestrator inside gVisor. The host keeps
the Vultr key and enforces the request budget. The output includes a usable
configuration and independent application helper, and is tested again inside
the original runner. [Real evidence](original-retail-agent-evidence-2026-11-07.md).

This is a reviewed adapter for one external agent, not automatic support for
arbitrary repository URLs. Its guide defines the reusable adapter contract and
the fixtures, state checks and application helper needed for another agent.

The [tau2 integration](../integrations/tau2/README.md) executes the unmodified
upstream `LLMAgent` runner with the exported profile. Both the migration and
frozen-verification commands accept `--runner tau2` after installing that
optional integration. The integration also checks original upstream tickets,
tools, policy and database goal assertions.

Other reviewed local integrations can use `--adapter your_package.adapter`.
Adapters define `CONTRACT`, `BASE_PROFILE`, `run_live`, resettable environment
factories and independent outcome assertions. Frozen verification additionally
requires `make_cases(seed, phase)`. Adapter code is trusted local code; this CLI
does not execute arbitrary unreviewed uploaded repositories.

## Inspect the evidence API

The [public Vultr preview](http://80.240.30.92) serves recorded run evidence and
downloadable compatibility configuration. Its public paid execution controls
are disabled. The CLI above is the live migration entry point.

```bash
python3 -m scripts.smoke_public --url http://80.240.30.92
```

For a local evidence API:

```bash
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./var/runs
```

The exact API shapes are documented in [the API contract](api-contract.md).
