# Real migration on Vultr — operator runbook

Refit's public site is deliberately read-only until there is a secure,
authenticated user-facing control plane. This runbook executes a **genuine,
billable migration** from the trusted Vultr VM, then publishes only its
completed result for anyone to inspect in the browser.

This is a working route to demonstrate the product's core loop, not a
substitute for a full public self-service product or external-agent importer.

## Prerequisites

- Ubuntu Vultr host with Docker and a registered gVisor \`runsc\` runtime.
- The private inference key at \`/etc/refit/inference.env\`, root-readable
  and never sent to the browser or GitHub.
- \`python:3.11-alpine\` pulled locally for disposable gVisor workers.
- Existing read-only Refit service configured by \`deploy/launch-public.sh\`
  with its non-root \`refit\` account and \`/var/lib/refit/runs\` directory.

Verify gVisor before doing any billable execution:

\`\`\`bash
cd /opt/refit-app
git pull --ff-only
bash deploy/verify-gvisor-on-host.sh
\`\`\`

For a zero-cost command preview:

\`\`\`bash
python3 -m scripts.operator_live \
  --domain refund \
  --source deepseek-v4.1-flash-1017 \
  --target muse-glimmer-30b
\`\`\`

## Run the actual migration

Run the following only **after consciously approving inference charges**.
It is designed for the already-configured root SSH session on the Vultr VM:

\`\`\`bash
cd /opt/refit-app
python3 -m scripts.operator_live \
  --domain refund \
  --source deepseek-v4.1-flash-1017 \
  --target muse-glimmer-30b \
  --max-requests 160 \
  --execute --publish
\`\`\`

This runs the existing refund business agent through Refit's shared migration
engine, all approved synthetic business tool simulations confined in disposable
gVisor containers. Only the host makes authenticated model calls. The host
independently replays business tool traces and verifies the final outcome.

The command emits observed source/target/repair/validation/holdout events
with actual pass counts. Model behavior can vary: **neither an 8/8 score nor
a successful repair is guaranteed on a new run.**

It will not silently fall back to regular Docker or in-process tool execution.
If gVisor is missing, the Docker image is missing, a worker fails to clean up,
or a business oracle is not independently satisfied, Refit must not approve
a compatibility patch.

The operator service uses a separate private spool directory:
\`/var/lib/refit/operator-runs\`. The public service cannot read an active
run, so a web-server restart cannot accidentally mark a still-running
operator job as interrupted.

After the job reaches a terminal status, \`--publish\` atomically copies the
result into the non-root web service's history, restarts only
\`refit-public\`, and checks the real local HTTP endpoint.

The terminal prints the new \`live-...\` run id. Open
\`http://80.240.30.92/\` and select the live run. It should appear in
\`GET /api/runs\`; details and event history are available through
\`GET /api/runs/{id}\` and \`GET /api/runs/{id}/events\`. A verified patch
is available at \`GET /api/runs/{id}/artifact\` **only if** the independent
business tests approve it.

Do not paste the inference key, operator token, host logins, or private
model responses into chat. Use only the run id and redacted status/report
when diagnosing failures.

## Evidence and limitations

A meaningful winning demonstration shows:
1. Real source model passes the protected scenarios.
2. The replacement model fails at least one scenario (if it genuinely does).
3. Refit diagnoses the failure and proposes a bounded configuration edit.
4. Fresh validation/holdout tests verify that edit.
5. Execution runs in gVisor with no leftover tool workers.
6. Exported compatibility artifact is tied to its model and business contract.

Do **not** claim universal agent support: current domains are synthetic refund
and deployment workflows. Do not claim confidentiality from gVisor alone.
Do not claim zero regressions outside the evaluated sample.

The public HTTP endpoint has not been upgraded to TLS. For now, keep its
\`REFIT_ENABLE_LIVE\` and \`REFIT_ENABLE_SANDBOX_DIAGNOSTICS\` flags
**disabled**; never send an operator credential through that page. The CLI
does not expose a paid browser action.

In the longer-term interface, a proper authenticated, HTTPS server-side
control plane can submit jobs and stream these same trusted event records.
The final React UI can replace all demo layouts without changing the engine.
