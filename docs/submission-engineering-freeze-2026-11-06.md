# Refit engineering freeze and judge acceptance — November 6, 2026

**Status: verified evidence available; one optional on-host frozen-patch receipt still unconfirmed.**

This is the handoff for the submission workstream. **Do not restart the migration-engine design, add frameworks, or run billable repair searches to produce more impressive numbers.**

## The two distinct, reproducible stories

1. **Verified repair transfer (external runner).** Refit's existing exported refund compatibility patch was used unchanged in the upstream tau2 agent runner. Across three predeclared fresh seeds, source DeepSeek passed **24/24**, unpatched Muse **13/24**, patched Muse **24/24**. This was a real Vultr inference evaluation, not a host-gVisor claim. [Evidence and limitations](framework-evidence-2026-11-06.md); [GitHub Actions run](https://github.com/Davemafy/refit/actions/runs/42257639812).
2. **Real on-host regression rejection.** The Vultr operator run **live-8faad4e25db3a36d** used isolated gVisor business-tool workers. Source passed 8/8 training; original Muse passed 7/8; a candidate passed 8/8 training but failed validation 7/8. The candidate was rejected, no patch could be downloaded, and all **48** worker cleanup receipts were checked. This is *not* a successful on-host adaptation. [External host acceptance](https://github.com/Davemafy/refit/actions/runs/42278943745); [Host acceptance detail](vultr-host-acceptance-2026-11-06.md).

The evidence supports both **a repair that passed independent tests** and **the engine refusing to publish a repair that did not pass**. Do not splice these into one fictitious run.

## Exact deployed release

The public read-only deployment at http://80.240.30.92 currently identifies itself as Git commit:

    e53feebd8f6d1d08595d23d3b0794aa814c60841

The checkout was externally confirmed clean. The submission source repository may be ahead: new test and evidence-recovery commits are *not* proof that the deployed Python service was restarted onto that revision.

For final acceptance, [public-smoke.yml](../.github/workflows/public-smoke.yml) pins the deployed SHA and [smoke_public.py](../scripts/smoke_public.py) checks: a healthy site, recorded artifacts, real published rejection, individual gVisor cleanup receipts, and **disabled public paid inference/diagnostics**. It sends no live execution requests.

**The environment remains HTTP-only and read-only.** Do not enable billing or send agent secrets over the public page.

## Recover the pre-existing host frozen-patch result — no new inference

A previous operator run began testing the archived fixed patch on the Vultr machine. The final result was not published in the public API, GitHub, or the recovered agent workspace. Its success is **not confirmed**.

The recovery command only reads existing JSON report files; it never loads an inference key, creates containers or calls a model.

On an **already authorized** VPS operator session, use a disposable checkout so the deployed application tree and its recorded startup SHA are untouched:

    audit="$(mktemp -d /root/refit-evidence-XXXXXX)"
    git clone --depth 1 https://github.com/Davemafy/refit.git "$audit/repo"
    cd "$audit/repo"
    python3 -m scripts.recover_frozen_evidence

The recovery tool checks /opt/refit-app, /opt/refit and /var/lib/refit/evidence for filenames containing frozen verification, including up to two nested directories. Alternatively give the previously recorded path using --report /path/to/report.json.

If the outcome is not_found, do not re-run inference just to make this status green. Search operator notes and process logs *locally*, without posting private provider responses or credentials.

For an existing report, the tool verifies the patch digest and contract, declared seed and phase coverage, per-trial aggregate totals, and unsafe attempts. Incomplete trials, budget exhaustion and failed reports cannot be relabeled as verified successful adaptations.

To retain only the safe summary on the host:

    python3 -m scripts.recover_frozen_evidence --output /var/lib/refit/evidence/recovered-frozen-summary.json

The output is written exclusively with permission mode 0600 and excludes full model transcripts. A verified summary means the *provided existing report's contents* were internally consistent; this is not cryptographic proof of the host on which the original model calls executed. Preserve its raw SHA-256 and trusted operator log separately if making an on-host provenance claim.

This step is **read-only** and does not restart the public service, reset Vultr resources, deploy code, or consume inference credits.

## Submission readiness

**Confirmed:** real Vultr inference, isolated host tools and cleanup, rejected patch safely withheld, separately successful tau2 patch transfer, durable evidence API, CI on Python 3.11 and 3.12, external revision-pinned read-only acceptance.

**Explicitly not claimed:** arbitrary third-party agent repository migration; an authenticated public self-service control plane; production security; success on untested agent workflow families; a passing result for the pending host-only frozen-patch test.

**Engineering freeze:** after passing repository CI and external acceptance, change only actual blockers. Keep the verified deployed SHA identified in every judge-facing artifact.

The product demonstration can proceed using the two validated stories above even if the missing host-only report cannot be recovered. No new inference is required to tell the truth about what Refit already does.
