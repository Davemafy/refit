# Refit

**Change the model. Keep the behavior.**

Refit helps developers migrate existing AI agents between language models without silently losing required tool-use behavior or business outcomes. It runs the original agent against source and replacement models, collects execution evidence, identifies regressions, tests bounded model-facing adaptations where the original application permits them, and withholds exports that fail independent verification.

Built for **Vultr Agent Rush 2026**. General-agent compatibility is the product direction; the execution modes and frameworks listed below are the **currently supported or verified subset**, not a claim of universal compatibility.

**[Open the live Refit workspace](https://80.240.30.92/app)** · [How to bring an agent](docs/bring-your-agent.md) · [Engineering evidence](#verified-results)

The HTTPS workspace includes a **read-only guest walkthrough** of a recorded, real Vultr migration. No sign-in is needed to inspect that example. Developers can create accounts without invitations to import source and authorize bounded inference; private projects, runs and exports remain account-scoped. The public example is recorded, not a live execution.

## How Refit works

1. **Bring an agent.** Import a pinned GitHub revision or a ZIP. Refit inspects source without executing it, finds likely application entry points and provider signals, and reports selected and excluded files.
2. **Define required behavior.** Confirm the original invocation and independent training, validation and holdout checks. The managed application path supports output, JSON, tool-call and selected application-local file-state checks.
3. **Run the original program.** Source and replacement models execute through Vultr inference while imported code runs in disposable gVisor containers.
4. **Diagnose and adapt.** Failed behaviors can trigger a bounded repair when the original agent exposes an explicitly permitted model-facing configuration seam.
5. **Verify and export.** Refit tests the candidate on independent cases and reruns the exported configuration in a fresh original-runtime process. A failed or unsupported migration retains evidence but **does not receive a verified export**.

The specialized refund and retail-agent integrations verify independent, stateful business outcomes. The generic self-service importer currently provides narrower declarative checks; it must not be represented as independently verifying arbitrary production databases or remote side effects.

## How Refit uses Vultr

| Vultr service | Role |
| --- | --- |
| **Cloud Compute** | Hosts the HTTPS application, Nginx, Python API, trusted controller, recorded evidence and Docker/gVisor workers on the Vultr VM. |
| **Serverless Inference** | Serves source-model calls, replacement-model calls and supported repair generation. The API credential remains on the trusted host, never inside imported-agent containers. |

## Architecture

```text
Browser ── HTTPS ──► Nginx (TLS and rate limits)
                         │
                         ▼
               Refit application API
                accounts · budgets · runs
                         │
                         ▼
               Trusted host controller ──────► Vultr Serverless Inference
                model broker · evidence              (source / target / repair)
                         │
                         ▼
              Disposable gVisor worker
                original agent and tools
            no external network · no model key
                         │
                         ▼
                Trusted outcome checks
                 validation · holdout
                         │
                         ▼
             Fresh original-runtime verification
                         │
                         ▼
               Verified export or rejection
```

The **host controller is trusted and outside gVisor**. The application process runs under a dedicated Linux account but currently has Docker-group access to launch workers; that privileged control-plane boundary remains a hardening task. The sandbox itself has no Docker socket or inference credential. See [architecture](docs/architecture.md) and [sandbox runtime](docs/sandbox-runtime.md).

## Verified results

The following are distinct experiments. They are evidence of the supported flows, **not an accuracy guarantee for arbitrary agents**.

| Experiment | Observed outcome | Evidence |
| --- | --- | --- |
| Synthetic refund agent, DeepSeek → Muse | Baseline replacement 5/8 training; repaired 8/8 training and validation; repaired holdout 8/8 vs 7/8 unchanged. Zero unsafe refund attempts in reported gates. | [First live repair](docs/live-evidence-2026-11-06.md) |
| Exported refund patch in the original external agent runner | Source **24/24**, unchanged replacement **13/24**, patched replacement **24/24**, zero unsafe attempts across three predeclared fresh seeds. | [Framework verification](docs/framework-evidence-2026-11-06.md) |
| Frozen patch on the Vultr host | Patched **8/8** vs unchanged replacement **5/8**; all **24** gVisor workers cleaned up. | [Host recovery evidence](docs/vultr-frozen-patch-recovery-2026-11-06.md) |
| Independently developed retail agent | Original **6/6**, replacement **6/6**, fresh exported configuration **2/2**. No repair was needed for this model pair. | [Retail evidence](docs/original-retail-agent-evidence-2026-11-07.md) |
| Two independent browser-initiated Python application imports | Source and target **3/3** each, fresh original-runtime export verification **1/1** each; model-only exports, not repairs. | [Application acceptance](docs/bring-your-agent.md#browser-acceptance--november-7-2026) |
| Candidate that failed independent validation | Repair was **rejected** and no verified patch was released. | [Host acceptance](docs/vultr-host-acceptance-2026-11-06.md) |

The synthetic refund holdout was not a pristine once-only blind statistical test; see the original evidence for its limits. Specialized stateful integrations and the self-service importer must not be conflated.

## Supported agents and limits

| Capability | Current state |
| --- | --- |
| **Managed Python 3.11** with non-streaming OpenAI-compatible Chat Completions | Verified with genuine imported applications and real Vultr inference. |
| **Pinned GitHub source ingestion** | Reads the pinned Git tree, selectively downloads and verifies required blobs, and skips common build outputs and assets. Supports application-directory and file selection. |
| **ZIP ingestion** | Streams up to **32 MiB compressed**; the selected execution snapshot is limited to **12 MiB**, **1,500 files** and **512 KiB per file**. |
| **Managed Node/TypeScript and Vercel AI SDK 7** | The pinned AI SDK 7 application passed a paid GLM → DeepSeek migration with original tools, file checks and fresh export verification. [Vultr receipt](https://github.com/Davemafy/refit/actions/runs/42416108155). |
| **Generic managed-agent checks** | Exact output, JSON fields, broker-observed tool calls/arguments/results, forbidden tools, and bounded application-local file effects. These do **not** prove arbitrary database or external-service state. |
| **Generic repairs** | Explicit original instruction-environment seams are implemented and tested; a successful independently verified paid repair through the self-service importer remains unproven. |
| **Developer-side connectors** | Trusted local Python and authorized loopback HTTP test services use the shared broker and evaluator. See the [connector contract](docs/bring-your-agent.md#developer-side-connectors). |

Streaming, arbitrary dependency installation, custom provider protocols, production database access and general external-service execution remain unsupported. Check the detailed [compatibility and ingestion guide](docs/bring-your-agent.md) before running an unfamiliar application.

## Quickstart: inspect recorded evidence without an inference key

Requires Python 3.11 or 3.12 for the development and offline-test commands.

```bash
git clone https://github.com/Davemafy/refit.git
cd refit
python3 -m unittest discover -s tests -p 'test_refit*.py'
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./runs
```

Open `http://127.0.0.1:8097/demo`. This is the recorded-evidence service, **not** a full local deployment of the public HTTPS Bring Your Agent app.

Real, billable migrations require a configured Vultr inference credential, gVisor runtime, operator authorization and bounded execution budgets. See the [developer MVP guide](docs/developer-mvp.md) and [Vultr deployment instructions](docs/public-deployment.md). **Never commit inference keys or imported application secrets.**

## Security and operating boundaries

- Imported code runs in disposable, resource-limited gVisor workers without external network access or host inference credentials. The host broker and evaluator remain trusted processes outside the sandbox.
- Registration and login are rate-limited. Live inference requires authentication and explicit authorization; there is no anonymous billable execution.
- Pinned source imports enforce path, secret-file, file-size and snapshot limits. Source selection and inclusion/exclusion receipts are inspectable.
- Account data and run evidence are owner-scoped. Per-account and global request ceilings and a single active migration protect current hosting capacity; they also limit concurrency.
- The current API-to-Docker privilege boundary warrants further separation before unrestricted production usage. Cleanup receipts are host-generated verification, not comprehensive kernel-syscall auditing.

## Documentation

- [Bring Your Agent: access, import, limitations and original-runtime verification](docs/bring-your-agent.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Sandbox runtime and isolation](docs/sandbox-runtime.md)
- [Developer MVP / operator setup](docs/developer-mvp.md)
- [Verified agent integration](integrations/retail/README.md)
- [Engineering history and earlier milestones](docs/engineering-history.md)

Developer-side connectors run from the CLI. The hosted workspace uses managed gVisor execution.
