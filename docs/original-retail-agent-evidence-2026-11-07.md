# An original external agent through Refit

Repository: [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench),
revision `033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`.
Agent: its original **retail customer-service agent**.

This integration runs the upstream `LLMAgent`, `UserSimulator`, `Orchestrator`,
retail tools, policy, database, task scenarios and evaluator. It does not use
Refit's own refund fixtures or rebuild the agent's business logic.
It is a customer-service simulation from an independent open-source repository,
not a claim of migration against a live merchant or arbitrary customer repository.

## Real observed comparison

The [original Vultr inference run](https://github.com/Davemafy/refit/actions/runs/42315996248)
completed **208 real API requests**, including customer-simulator calls.
All 14 native case executions passed the original state evaluator and matched
the independently derived full-database goal hashes. Those are six unique
upstream tasks, plus repeated original-runner checks, not 14 unique tasks.

| Gate | Source DeepSeek | Replacement GLM |
| --- | ---: | ---: |
| Training: original tasks 73, 75 | 2/2 | 2/2 |
| Validation: original tasks 77, 79 | 2/2 | 2/2 |
| Holdout: original tasks 80, 85 | 2/2 | 2/2 |

Original-runner execution using the exported configuration also passed 2/2 in
that initial run. Reported upstream tool errors were zero. The adapter counts
tool errors conservatively against acceptance; it does not infer universal
policy compliance merely from fluent model text.

The model pair was **compatible on this sample**. Refit correctly generated no
instruction repair. The usable export changes the model configuration to GLM
and preserves original instructions, policy, tool functions and parameter
schemas. No regression was invented to produce a more dramatic repair result.

## Delivery failure and exact recovery

The original run withheld its export because the container's final result was
truncated, despite its completed business checks. Its
[complete retained record](../data/evaluations/retail-native-001-partial.json.gz)
contains every actual returned model response and every completed native case.

The failure was reproduced without new inference. The final frame stopped at
exactly **65,536 bytes**; the worker was healthy, had not been OOM-killed, and
remained alive waiting for acknowledgement. A compact
[diagnostic receipt](../data/evaluations/retail-native-delivery-diagnostic.json)
records that observation and cleanup.

The emitter now handles partial writes explicitly in bounded byte chunks and
requires acknowledgement of the complete final result. Its regression test
forces repeated short writes of a large Unicode payload. Native-framework
memory headroom and collection of previous case environments are also bounded
explicitly; they do not change the business oracle or acceptance thresholds.

The [successful recovery](https://github.com/Davemafy/refit/actions/runs/42318628060)
matched **all 208 provider requests by exact canonical hash** before returning
each saved response. A changed request fails rather than falling back to
inference. It recovered the shared-engine result and usable export through the
original runner. This recovery is explicitly recorded as
`recorded_transport_recovery`, with **zero new inference requests**; it is not
presented as another live model-performance trial.

The [recovered full report](../data/evaluations/retail-native-001-recovered.json.gz)
retains the source revision, image identity, original case transcripts, real
response provenance, exact-match replay accounting, actual `runsc` runtime,
container exit state and verified cleanup receipt.

## Fresh verification after applying the export

The [final native-runner acceptance](https://github.com/Davemafy/refit/actions/runs/42318995816)
loaded the exact exported JSON and application helper, then ran tasks **80 and
85** again through the original Orchestrator with **new real Vultr responses**.
It passed **2/2**, with zero tool errors and matching complete goal states.
This step did not use cached model responses or conduct another repair search.

It used **33 actual requests** within its separately declared 64-request cap.
The entire effort used **208 + 33 = 241 actual requests**, below the original
400-request allowance. Exact-match recovery consumed zero additional requests.
Token and dollar costs are not measured by this transport.

The [complete fresh acceptance record](../data/evaluations/retail-native-export-fresh-2026-11-07.json.gz)
records the actual `runsc` runtime, normal container exit, verified cleanup,
every real model response and both original-runner outcomes. Its exported
configuration is byte-for-byte identical to the recovered export:

```text
ec7e9b87a6c64fae3141755a136bf62be3a6f6225943e26fa23fbe98cfbf49e8
```

This closes the journey: independent original agent → real model comparison →
no unnecessary repair → usable model configuration → fresh successful
execution after applying it in the original framework. The execution plan is
disabled after acceptance; later code commits cannot repeat the paid run.

## Apply and reproduce

- [Verified configuration](../integrations/retail/verified/agent-config.json).
- [Downloadable export package](../integrations/retail/verified/agent-export.zip)
  containing the exact configuration, independent helper and checksums.
- [Application helper](../integrations/retail/apply_config.py), with no Refit
  imports; copy it with the JSON into the approved original checkout.
- [Integration guide and commands](../integrations/retail/README.md).
- [Predeclared manifest](../integrations/retail/manifest.json).

The application helper checks the baseline configuration and protected policy
and tool-schema fingerprints before changing model-facing configuration.
Execution uses the original framework, not Refit's internal tool-use loop.
The guide documents both the credential-isolating broker and the native
LiteLLM provider configuration needed in an original trusted deployment.

The ordinary CLI remains inspect-only unless `--execute` is supplied. A
separate `--verify-export` mode applies an existing configuration to the full
original runner without another repair search. All billable calls, including
customer-simulator calls, share an explicit hard request cap; provider errors
do not trigger automatic paid retries. Failure retains evidence and withholds
unverified configuration exports.

## Supported integration boundary

Supported here: the pinned original retail agent, its six declared tasks and
full native runner through a reviewed container adapter. This does not prove
all retail workflows, unknown agents, unseen business families or production
reliability. This particular pair demonstrated verified compatibility, not a
newly generated repair to the external agent.

For another agent, supply a reviewed image and adapter with extracted model
configuration, immutable tool and policy contracts, disjoint native test cases,
initial/expected state fingerprints, original-runner execution, independent
outcome checks and a configuration application helper. The shared migration
gates and host credential/budget broker are reused. Imported code runs inside
gVisor with no network, host mounts, Docker socket or inference credential.
Host-side adapter imports through the legacy trusted `--adapter` path are not
a safe substitute for this boundary.

The current public deployment remains the pinned, read-only demonstration.
This external workflow is a developer/operator CLI integration, not a hosted
arbitrary-repository upload service. Integrity digests bind the preserved
records and configuration; they are not signed host attestation.
