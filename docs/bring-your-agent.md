# Bring your agent

Refit has two separate services on the same Vultr VM: the public **HTTP
read-only evidence site** and the **HTTPS invite-only application** at
https://80.240.30.92/bring. The application imports source, executes the
original program against two Vultr models in gVisor, verifies the generated
configuration in a fresh native process and enforces account ownership.
The original loopback operator mode is retained for administration.

## Public HTTPS account access

**For an invited developer or judge:** open
https://80.240.30.92/bring in a normal browser, register using a
one-time invite, sign in and import a pinned public GitHub repository or
ZIP. Confirm the agent invocation and three independent evaluation cases,
choose the source and replacement models, authorize a capped run, then
inspect live evidence and download a verified artifact or an explicit
failure report. No SSH tunnel or shared operator token is needed.

**For the host operator only:** generate a short-lived one-time invite
from the deployed checkout under /opt, running the command as the
`refit-application` service user:

```bash
sudo -u refit-application python3 -m scripts.application_accounts \
  --state /var/lib/refit-application
```

Give each judge their own invite privately; never commit invite or
session tokens. Anonymous visits can load the sign-in page but cannot
read another account's project, run, event stream, evidence or export.
The HTTPS TLS certificate is a short-lived Let's Encrypt IP-address
certificate with an automatic renewal timer.

The externally executed zero-inference check
[`scripts/smoke_platform_https.py`](../scripts/smoke_platform_https.py)
validates TLS, the public sign-in page, anonymous session mode and access rejection,
operator-token bypass rejection and certificate freshness on each main push.
The browser sign-in-to-export acceptance was separately performed by the
operator on November 7 with two invited accounts and a Python application,
using seven real inference requests; that account-run browser artifact
has not yet been independently archived in this repository.

## Judge-facing live walkthrough

The following is the **legacy operator-only tunnel option**. Invited judges
should use the public HTTPS account path above; they do not need SSH or the
operator access token.

1. Using an SSH account authorized to forward ports to the Vultr VM, open
   `ssh -N -L 8098:127.0.0.1:8098 root@80.240.30.92`.
2. Open [Bring your agent](http://127.0.0.1:8098/bring). Obtain the operator token
   privately on the host from `/etc/refit/application.env`. Paste it into the
   page. The token stays in the page for this session.
3. Inspect GitHub repository `simonw/llm` at
   `b9786a2daa44a995ff7719c655c5338bf685d551`. Refit detects the Python
   CLI, model configuration seam and original `llm_version` tool.
4. Select `deepseek-v4.1-flash-1017` and `glm-5.2`. Approve the 24-request
   ceiling and click **Run migration**. Follow the real model, case, tool and
   cleanup events. Each terminal run can be reopened by its ID.
5. Download the verified configuration when the fresh export check passes.
   On failure, download the evidence and inspect the failed phase.

The operator service requires authentication and binds to loopback. The
separate public account ingress on port 443 is already deployed with HTTPS,
account scoping and SSE buffering disabled. Never expose port 8098 directly. The host installer is
`bash deploy/launch-application.sh` from a checkout under `/opt`, with Docker,
gVisor and `/etc/refit/inference.env` configured. It allows one active run,
up to 24 requests per run and 48 request slots reserved per UTC day. There
are no automatic paid retries.

## Supported import and execution

| Entry | Contract |
| --- | --- |
| GitHub | Public pinned commit. For a private repository, supply a scoped read token for the archive request. The service discards the token after the request and strips it on redirect to GitHub's signed archive URL. |
| Project ZIP | At most 4 MiB compressed, 12 MiB expanded, 1,500 entries and 512 KiB per file. Traversal, symlinks, special files, known credential files and dependency caches are rejected. |
| Local CLI | `python -m scripts.application_cli /path/to/project --port 8098` imports to a locally running operator service. Set its `REFIT_APPLICATION_TOKEN`. Supply `--authorize-requests 24` to start and `--export config.json` to save a verified result. Source can stay on the developer's machine with local Docker and the same gVisor image. |

The production-verified native runtime is Python 3.11, a Python module
entry point and non-streaming OpenAI-compatible Chat Completions. The
reviewed image includes LLM 0.37.1 and its dependencies. A reviewed Node
runtime additionally supports pinned TypeScript/JavaScript CLI programs using
the Vercel AI SDK 7 tool loop and approved dependencies, without running
untrusted dependency-install scripts. It passes the original tool loop,
training/validation/holdout and fresh export in a **zero-inference gVisor
preflight**, but the first paid DeepSeek run failed to call the required
`read_file` tool and Refit correctly withheld export. Do not describe this as
a successful paid TypeScript migration. The LLM preset discovers the native CLI and uses its
`extra-openai-models.yaml` seam. Other Python agents may supply
`{"module":"agent","args":["{prompt}"],"cases":[...]}` in the form or through
`--setup setup.json`. Each case includes a unique `name`, a `split` of
`train`, `validation` or `holdout`, a `prompt` and expected `stdout`.
Supply all three splits. Store evaluation files outside the source ZIP.
The application must honor `OPENAI_BASE_URL` and `OPENAI_MODEL`. Unreviewed TypeScript dependencies, streaming, custom provider protocols,
live external tools and persistent production services require additional
runtime support.

The app receives only the current case input. Other cases and expected
outputs remain host-side. Fresh containers give each model a clean source
snapshot and state directory. The broker sends model messages to Vultr and
keeps its credential outside the sandbox. It enforces the selected model,
request caps and a fixed inference envelope. Generic environment-seam
applications can receive compatible exports. An instruction repair requires
an explicit native instruction seam, currently available for the LLM preset.

## Use the native export

For the verified LLM run, with the original app installed at the pinned
revision, create a clean native model configuration directory:

```bash
export LLM_USER_PATH="$(mktemp -d)"
python -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["extra-openai-models.yaml"],indent=2))' app-3df57a3a263249eb-artifact.json > "$LLM_USER_PATH/extra-openai-models.yaml"
llm keys set vultr
llm prompt --no-stream --no-log --chain-limit 2 -m glm-5.2 --tool llm_version -- 'Use llm_version. Reply with only the version it returns.'
```

The configuration contains the provider URL and key alias. Supply your own
key with the original app. The Refit fresh check loaded the exported model
and arguments into the original runner with its endpoint routed through the
isolated broker.

## Live evidence · November 7, 2026

Vultr run `app-3df57a3a263249eb` started through the deployed authenticated
HTTP API at Refit revision `0d4d2bf2cf59a63eddab6b80727d8bae03090a59`.
The deployed runtime image was
`sha256:12f275f8989d1dcd68485e490f89de90d26e79436a3f1cddf92feab674c6bf92`.

| Check | Observed |
| --- | --- |
| Import | 122 files in 0.279 s, source SHA-256 `597977e191dc7e02b35ead9879958d1502b79ecb17121ad9ed8283ee43393470` |
| Runtime preparation | 0.024 s for pinned image lookup. First container start event to first inference request was 1.032 s. |
| Execution | 25.797 s and 14 Vultr requests of 24 authorized |
| Source and replacement | 3/3 each. Every partition independently matched stdout and observed the original `llm_version` tool result. |
| Export | `compatible_on_sample`, fresh GLM verification 1/1 in 3.094 s and 2 requests. No repair was needed. |
| Cleanup | All seven live gVisor containers verified absent. The separate hostile and runaway probes used zero inference, with 2/2 verified cleanup. |
| Resources | One case container at a time. Network none, unprivileged UID, read-only root, 2 CPUs, 4 GiB memory ceiling, 128 PIDs and 128 MiB temporary filesystem. |

[Live evidence](../data/evaluations/application-live-2026-11-07.json.gz) and
[host containment receipts](../data/evaluations/application-containment-2026-11-07.json)
are durable snapshots of the observed runs. The uncompressed live report
SHA-256 is `56bb71e8c483671b318b4c810a683734c2d995e486f0f8c0f560399bd5e4f212`.

The three evaluation partitions vary requests for one real tool behavior.
They do not establish compatibility for unrelated application tools or
business workflows. Igor's pinned `dev` revision
`36b3e323e79a66af86b24fd149f93cc95e7a37b1` uses the TypeScript Vercel AI SDK
ToolLoopAgent with provider routing and external services. Its execution
requires a Node runtime and offline tool and state seams. The current release
covers its source inspection, with execution blocked at setup. A repaired
regression in an independent application and a private GitHub import using
a real repository token remain unverified. The existing mini-SWE rejection
remains recorded separately.

[Engineering CI](https://github.com/Davemafy/refit/actions/runs/42352597082),
[application CI](https://github.com/Davemafy/refit/actions/runs/42352597116)
and [public acceptance](https://github.com/Davemafy/refit/actions/runs/42352597137)
passed on deployment revision `eb369028c43cdf28480862f00ea59ff32857e089`.

The deployed ZIP path accepted a one-file TypeScript fixture
(`import-7cfad4f61d3a0029`). Starting it returned HTTP 422
`setup_required` with the Python and OpenAI-compatible boundary requirement.
It used zero model requests.

## Browser acceptance · November 7, 2026

Firefox 142 ran against the deployed Vultr service through an authenticated
SSH tunnel on revision `6dbadb06a05e007e5565198b3f438ec22959f1cf`.
It rejected an invalid operator token, inspected the pinned LLM GitHub
repository and prevented a start while the authorization checkbox was clear.
Both live starts were single POSTs initiated by the browser Run button.

| Run | Input | Import | Execution | Inference | Verification |
| --- | --- | ---: | ---: | ---: | --- |
| `app-6706a75ba00f0277` | `simonw/llm`, GitHub at `b9786a2daa44a995ff7719c655c5338bf685d551` | 1.005 s | 22.271 s | 14 / 16 | Source 3/3, target 3/3, fresh native export 1/1 |
| `app-4556b7ce134da13c` | Independent electromagnetics knowledge-base CLI, uploaded ZIP, `src.qa` and no preset | 0.001 s | 18.981 s | 7 / 8 | Source 3/3, target 3/3, fresh native export 1/1 |

Both runs used `deepseek-v4.1-flash-1017` → `glm-5.2`, returned
`compatible_on_sample`, and verified cleanup for all seven gVisor
containers per run. These are model-only exports. The LLM browser observed
live tool and inference events. Its original 20-second test timeout fired
before the 22-second run finished. Firefox reopened that same run and
downloaded both outputs. The generic browser test ran start to download
with a longer deadline, then reloaded and reopened its run from the URL.
The two attempts used 21 requests against 24 authorized. The two prior
read-only browser checks did not start inference.

[LLM evidence](../data/evaluations/application-browser-llm-2026-11-07.json.gz) ·
[Generic evidence](../data/evaluations/application-browser-generic-2026-11-07.json.gz) ·
[Captured Firefox outcome](../data/evaluations/application-browser-generic-2026-11-07.jpg)

The generic ZIP contains unmodified application source and wiki files from
[`rma67274-boop/wulianwang_zuoye_mrp` at `78e234c09412cabf6a1d6f901329c5b66360d946`](https://github.com/rma67274-boop/wulianwang_zuoye_mrp/tree/78e234c09412cabf6a1d6f901329c5b66360d946).
The full repository includes a 5.1 MB PDF and exceeds the 4 MiB import cap.
A runtime-only ZIP preserves the original entry point and data. The
browser supplies three operator-owned checks for different source formulas
and page citations. The application archive excludes those checks and
runs with no app-specific adapter. Its native export sets `OPENAI_BASE_URL`
and `OPENAI_MODEL` for the original `python -m src.qa` command. Use your
own API key when applying it locally. The deployed live broker used isolated
loopback endpoints for the original-runtime check.

Reproduce the archive without touching production state:

```bash
git init qa-source
git -C qa-source fetch --depth=1 https://github.com/rma67274-boop/wulianwang_zuoye_mrp.git 78e234c09412cabf6a1d6f901329c5b66360d946
git -C qa-source archive --format=zip FETCH_HEAD src/qa.py wiki test_all_features.py > qa-agent.zip
```

The tested ZIP SHA-256 is
`ff329acccdc47917ab9e951fb39d88762d0a31bd58fae6694f2724905a26d980`.
The normalized source digest is
`sha256:d5245d53b14cb6fcff6ac47992b5b069861033b8d1d4f210cf265c8b2c1488a3`.

With the private tunnel open, the recorded walkthrough can use either run
ID above without spending inference. The [browser harness](../tests/browser_application.mjs)
repeats the LLM import, checks authorization and downloads the saved run by
default. Set `REFIT_APPLICATION_TOKEN` locally. Use
`REFIT_BROWSER_REOPEN=app-6706a75ba00f0277` for the browser-started LLM run.
Only pass `--execute` (16 requests) or `--execute-generic` with
`REFIT_GENERIC_ZIP=/path/to/qa-agent.zip` (8 requests) after reserving the
budget. The verified deployment uses a private tunnel for operator
demonstrations. Public evidence and authenticated execution remain separate.

The [Figma architecture](https://www.figma.com/design/jh0XDbYZzwv90vAOnWw0Zu/Untitled?node-id=56-2)
guided the persistent run ID and outcome/evidence separation. The recorded-only
board predates this live service. Both verified compatibility and verified
repair may export when fresh native verification passes.
