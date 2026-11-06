# Exported patch in the original tau2 agent runner

[Live execution](https://github.com/Davemafy/refit/actions/runs/42257639812)
applied Refit's existing refund compatibility receipt through the unmodified
upstream `tau2.agent.llm_agent.LLMAgent.generate_next_message` method. The upstream
revision was `033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`.

No repair was generated or selected during this run. Seeds `723001`, `723002`
and `723003` were declared before execution. The same source, unchanged target
and fixed patched target received equivalent fresh scenario states and wrapped
requests. Models were `deepseek-v4.1-flash-1017` and `muse-glimmer-30b`.

| Seed | Source | Unchanged Muse | Muse with exported patch |
| --- | --- | --- | --- |
| 723001 | 8/8 | 4/8 | 8/8 |
| 723002 | 8/8 | 4/8 | 8/8 |
| 723003 | 8/8 | 5/8 | 8/8 |
| Total | 24/24 | 13/24 | 24/24 |

There were zero unsafe attempts in all three configurations. All declared trials
are preserved, including the unmodified model's failures. Across these samples
the unchanged target completed 54.2% of tasks; the fixed patch completed all 24.
This is a sample result, not a population reliability estimate.

The same run additionally executed three original upstream mock-domain tickets
using the original upstream tools, policy and goal actions. Both models passed
3/3, including state assertions and the required human transfer for unsupported
deletion. These are integration smoke tests, not a full conversational tau2
benchmark score or proof of a production customer integration.

The run used **201 real Vultr model requests** against one shared 400-request
cap, with 201 observed upstream runner steps. Of those calls, 187 were the
three-seed refund evaluation and 14 were original-fixture checks. The existing
patch receipt was validated against the original contract, baseline and target
model before application.

Full transcripts and independent state verdicts are preserved in
[`data/evaluations/tau2-frozen-verification-2026-11-06.json.gz`](../data/evaluations/tau2-frozen-verification-2026-11-06.json.gz).
The integration installation, boundary and commands are documented in
[the integration guide](../integrations/tau2/README.md).

This demonstrates patch transfer to an independently implemented agent runner
and repetition across fresh states within known workflow families. It does not
establish new workflow-family coverage, second-domain repair, arbitrary-agent
compatibility or production deployment of a customer agent.

## Public Vultr endpoint

A separate [independent HTTP verification](https://github.com/Davemafy/refit/actions/runs/42257993155)
passed all nine checked routes at `http://80.240.30.92`: homepage, health,
capabilities, run listing, both recorded run details, exported refund artifact,
intent interpretation and event history. The evidence API is read-only for paid
execution. This check does not assert that the newest engine commit was deployed
to that host or that host-specific gVisor containment was verified.

The route observations are saved in
[`data/evaluations/vultr-public-smoke-2026-11-06.json`](../data/evaluations/vultr-public-smoke-2026-11-06.json).
