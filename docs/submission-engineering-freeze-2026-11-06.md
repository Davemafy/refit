# Refit engineering freeze and judge acceptance — November 6, 2026

**Status: controlled developer MVP ready; on-host frozen-patch success recovered and verified.**

This is the handoff for the submission workstream. **Do not restart the migration-engine design, add frameworks, or run billable repair searches to produce more impressive numbers.**

## The distinct, reproducible stories

1. **Verified repair transfer (external runner).** Refit's existing exported refund compatibility patch was used unchanged in the upstream tau2 agent runner. Across three predeclared fresh seeds, source DeepSeek passed **24/24**, unpatched Muse **13/24**, patched Muse **24/24**. This was a real Vultr inference evaluation, not a host-gVisor claim. [Evidence and limitations](framework-evidence-2026-11-06.md); [GitHub Actions run](https://github.com/Davemafy/refit/actions/runs/42257639812).
2. **Real on-host regression rejection.** The Vultr operator run **live-8faad4e25db3a36d** used isolated gVisor business-tool workers. Source passed 8/8 training; original Muse passed 7/8; a candidate passed 8/8 training but failed validation 7/8. The candidate was rejected, no patch could be downloaded, and all **48** worker cleanup receipts were checked. This is *not* a successful on-host adaptation. [External host acceptance](https://github.com/Davemafy/refit/actions/runs/42278943745); [Host acceptance detail](vultr-host-acceptance-2026-11-06.md).

3. **Frozen patch verified on the actual Vultr host.** The unchanged archived patch passed **8/8**, versus unmodified Muse **5/8** and source **8/8**, on predeclared holdout seed `605120371`. The recovered original report records **63** inference requests, zero unsafe attempts, and **24** gVisor workers with verified cleanup. Recovery spent no new inference credits. [Full recovered evidence and offline reproduction](vultr-frozen-patch-recovery-2026-11-06.md).

The evidence supports both **a repair that passed independent tests** and **the engine refusing to publish a repair that did not pass**. Do not splice these into one fictitious run.

## Exact deployed release

The public read-only deployment at http://80.240.30.92 currently identifies itself as Git commit:

    e53feebd8f6d1d08595d23d3b0794aa814c60841

The checkout was externally confirmed clean. The submission source repository may be ahead: new test and evidence-recovery commits are *not* proof that the deployed Python service was restarted onto that revision.

For final acceptance, [public-smoke.yml](../.github/workflows/public-smoke.yml) pins the deployed SHA and [smoke_public.py](../scripts/smoke_public.py) checks: a healthy site, recorded artifacts, real published rejection, individual gVisor cleanup receipts, and **disabled public paid inference/diagnostics**. It sends no live execution requests.

**The environment remains HTTP-only and read-only.** Do not enable billing or send agent secrets over the public page.

## Recovered host result — no new inference

The original host report and operator wrapper are now preserved in the
[recovery bundle](../data/evaluations/vultr-host-frozen-recovered-2026-11-06.json.gz).
See the [recovery detail](vultr-frozen-patch-recovery-2026-11-06.md) for raw report
hashes, explicit runner-field normalization, reconciled request totals, fresh
cleanup observation, and an offline validation command.

The recovery did not deploy code, restart the public service, or run inference.
The public service still identifies the exact release above. Its archived patch
matches the artifact used in the successful frozen-patch test.

## Submission readiness

**Confirmed:** real Vultr inference, isolated host tools and cleanup, rejected patch safely withheld, separately successful tau2 patch transfer and on-host frozen-patch verification, durable evidence API, CI on Python 3.11 and 3.12, external revision-pinned read-only acceptance.

**Explicitly not claimed:** arbitrary third-party agent repository migration; an authenticated public self-service control plane; production security; success on untested agent workflow families.

**Engineering freeze:** after passing repository CI and external acceptance, change only actual blockers. Keep the verified deployed SHA identified in every judge-facing artifact.

The product demonstration can proceed using the separately identified experiments above. Use the preserved evidence without repeating paid evaluations.
