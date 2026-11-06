# Refit sandbox execution: operator runbook

**Current security boundary:** Real Vultr-model-generated Python runs in a
disposable, isolated Docker container. A separate opt-in path now executes
the **actual refund and deployment agent tool calls** in fresh Docker workers,
while model requests and repair approvals remain on the host. Both paths are
verified on GitHub runners; the Vultr VM has not yet been verified. This
does not support running arbitrary external agents.

## How it works

- Host-only Vultr Serverless Inference key and model requests.
- Host asks a Vultr model to write Python that analyzes actual migration evidence.
- Host launches one Docker container for the generated program.
- Container gets only generated code and bounded migration input JSON.
- An independent host oracle recomputes expected diagnostic results.
- Host collects exit status, hashes, stdout/stderr and verifies container absence.

Docker flags include --network none, --read-only, --user 65534:65534,
--cap-drop ALL, --security-opt no-new-privileges, pids 32, memory 128m,
CPUs 0.5, no extra swap, restricted tmpfs and no Docker socket or secret mounts.
The host also caps execution time and captured output. It forcibly removes
the named container on timeout or exit.

**Limitations:** Docker shares the host kernel. The optional runsc runtime uses
gVisor only if separately installed and registered on the target Docker host.
The hash-chained run record is tamper-evident for recorded events, not kernel
syscall auditing or proof that every denied operation was observed.

## Container proof, no model calls

From the repository root, on a Docker-capable Linux machine:

    docker pull python:3.11-alpine
    python3 -m scripts.sandbox_runner --fixture safe
    python3 -m scripts.sandbox_runner --fixture hostile
    REFIT_TEST_DOCKER=1 python3 -m unittest tests.test_refit_sandbox -v

The hostile fixture tries to read a host inference key file, detect an
inference-key environment variable, resolve DNS, connect to an external IP
and write to the read-only root filesystem.

Verify the observed denial/absence messages, ledger_valid=true,
container_removed_verified=true and runtime identity in the JSON.

GitHub Actions runs these actual Docker tests in the sandbox-containment job
and uploads two short-lived JSON reports. **This proves Docker containment on
GitHub's runner, not yet on the Vultr VM.**

## One model-generated code execution on the Vultr VM

The operator can run one bounded, paid Vultr Serverless Inference call with:

    python3 -m scripts.sandbox_diagnostics \
      --recorded refund \
      --model deepseek-v4.1-flash-1017 \
      --runtime runc \
      --output ./var/runs/refund-sandbox-diagnostic.json

The host loads the inference key privately from /etc/refit/inference.env.
The container never receives it. The generated program analyzes scores from
the archived real Vultr model migration and must pass an independent host
check of its output.

## Minimal UI interaction endpoint

The same-origin HTTP backend can enable the restricted feature with these
server-side environment variables:

    REFIT_ENABLE_LIVE=1
    REFIT_ENABLE_SANDBOX_DIAGNOSTICS=1
    REFIT_SANDBOX_RUNTIME=runsc
    REFIT_RUN_TOKEN=<operator-held high-entropy token>

An authorized operator sends:

    POST /api/runs/recorded-refund-2026-11-06/diagnose
    Authorization: Bearer <operator-held token>
    Content-Type: application/json

    {}

The server returns a new diagnostic run id. The UI polls
GET /api/runs/{id}/events?after=N and then GET /api/runs/{id}.
The resulting sandbox_diagnostic contains generated_code, expected,
observed, verified and all execution records.

The endpoint accepts NO user-supplied code, arbitrary agent modules, model IDs
or repository URLs. Runs require an operator token, are concurrency-limited
and consume at most one Vultr model request each.

Full migrations can also attach a sandbox_diagnostic when feature-enabled.
To isolate the **built-in agent's actual tool calls** during a full migration,
also set REFIT_USE_TOOL_SANDBOX=1. The server then creates one fresh,
restricted Docker worker per replay scenario, sends tool calls as JSON over
stdin/stdout, keeps the Vultr key and model client on the host and verifies
worker container removal. The server fails closed if Docker or the selected
runtime is unavailable. Do not treat an enabled flag as containment proof;
inspect report.execution_boundary in the completed run.

To test the actual worker protocol on a Docker-capable Linux host:

    REFIT_TEST_DOCKER=1 python3 -m unittest tests.test_refit_tool_gateway -v

This parity test runs the same real refund and deployment tool calls in
Docker and compares their results against the original trusted in-process
business oracles. It has passed in GitHub Actions but **still needs to run
on the actual Vultr VM**.

Use REFIT_SANDBOX_RUNTIME=runsc after installing and verifying gVisor.
An explicit fallback to runc must be labeled as ordinary Docker isolation.


## Verified gVisor option (preferred)

The CI workflow [Verify gVisor Containment](../.github/workflows/gvisor-verify.yml)
installs the upstream signed gVisor package, registers the Docker `runsc`
runtime and runs actual safe/hostile probes with `--runtime runsc`.
The reproducible evidence is uploaded to the workflow run as JSON.

**This GitHub CI proof does not prove the Vultr VM has gVisor installed.**

The operator can repeat the same check on the existing Ubuntu Vultr VM:

```bash
# Run as root on the Vultr VM, not on your laptop.
if test -d /opt/refit-app/.git; then
  git -C /opt/refit-app pull --ff-only
else
  git clone https://github.com/Davemafy/refit.git /opt/refit-app
fi
cd /opt/refit-app
bash deploy/install-gvisor.sh
bash deploy/verify-gvisor-on-host.sh
```

The installer adds the signed gVisor apt repository and registers `runsc`.
It reloads Docker configuration but does **not** change Docker's default
runtime or deploy any service. Review the commands before running them on a
host with other production workloads.

The verifier saves exact runtime/version, real safe and hostile stdout,
process exit status, container-removal verification and hashes to a private
folder under `/var/lib/refit/evidence`. No secret values are required or
collected. Upload **sanitized** evidence for the demo; do not publish host
environment metadata if it identifies your infrastructure unnecessarily.

The backend's enabled sandbox diagnostic now defaults to `runsc`, and fails
if that runtime is unavailable. For an explicit Docker-only fallback,
the operator may set `REFIT_SANDBOX_RUNTIME=runc`, but the UI must label the
weaker container boundary honestly. No automatic downgrade.

gVisor runs a userspace application kernel and supports the `systrap`
platform in VMs without nested virtualization. It is not the same as a
separate-kernel microVM (Firecracker/Microsandbox).

## November 6 live proof (GitHub runner, not the Vultr VM)

The [one-call Vultr + gVisor experiment](https://github.com/Davemafy/refit/actions/runs/42227479472)
successfully requested **one real code-generation response** from
`deepseek-v4.1-flash-1017` through Vultr Serverless Inference. The generated
Python executed under Docker's `runsc` runtime. The host-side verifier
independently agreed with its diagnosis:

- Original training comparison: 8/8 source vs. 6/8 target, delta 2.
- Target failures: `ineligible` and `timeout_after_commit`.
- Holdout improvement: 7/8 to 8/8, delta 1.
- Generated code: completed successfully; Docker container absence checked.
- The workflow archives its source code, expected/observed diagnostic,
  gVisor execution ledger, and runtime metadata in a downloadable Actions artifact.

The actual migration report is previously recorded empirical evidence;
only the diagnostic code-generation and sandbox execution were live in this
new run. This **does not** prove the complete migration agent's business tools
were isolated, and it is not a Vultr-VM deployment proof.

The experiment manifest is now set to `run_live=false` after the successful
single-request run; avoid automatically repeating billable inference.

## Independent business correctness: host-side replay

The built-in refund and deployment workflows now support separate per-scenario
sandbox workers in `scripts/sandbox_tool_gateway.py`. The host retains all
Vultr model credentials and receives JSON tool results via bounded pipes.

**Crucially, the worker's success verdict is not sufficient.** For these
trusted, deterministic built-in workflows only, the host replays the worker's
reported tool-call sequence against fresh protected business state and checks
every tool result, full event trace, and final verdict. A mismatch makes the
scenario fail closed. Offline tests deliberately forge both a result and a
worker verdict to verify rejection. This does not authorize running untrusted
third-party tools on the host, nor does it prove worker execution authenticity.

The independent gVisor workflow also tests the **entire deployment-agent
migration** under `runsc` with a scripted model provider (zero billable inference).
It verifies source success, observed target regression, repaired validation
and holdout success, and no leftover worker containers. This is separate
from the live one-call Vultr code-generation proof.

These checks are complementary: security containment does not imply business
correctness, and a correct business verdict does not imply containment.

## Still required for a competition-ready claim

1. Verify the runner and capture actual containment evidence on the Vultr VM.
2. Deploy and test the full public UI-to-backend interaction on that VM.
3. Prove that the integrated code-writing agent step operates on live inference.
4. Make explicit what is sandboxed versus not; never imply all imported agents
   are supported or that business safety is guaranteed from an eight-case demo.
5. Record the live execution and contain an actual hostile attempt for the video.

Avoid exposing operator tokens or the Docker control socket through the UI.
