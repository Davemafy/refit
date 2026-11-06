# Refit Vultr-host acceptance — November 6, 2026

**Product:** Refit — Change the model. Keep the behavior.

**Observed public service:** http://80.240.30.92/

**External observer:** GitHub-hosted Python 3.12 runner, not a process on the Vultr VPS.

**Verified external run:** [GitHub Actions #42275235674](https://github.com/Davemafy/refit/actions/runs/42275235674).

## Independently checked

The independent HTTP client requested the deployed page, API health,
capabilities, both recorded examples, the recorded compatibility artifact,
public event history, and the published **real** host migration.

| Claim | Evidence from external run |
| --- | --- |
| Server responded from the public Vultr URL | HTTP requests passed |
| Running server version | `e53feebd8f6d1d08595d23d3b0794aa814c60841` |
| Deployed checkout | `tracked_files_clean: true` |
| Published operator migration | `live-8faad4e25db3a36d` |
| Published operator verdict | `repair_rejected_validation` |
| Container runtime | `runsc` (gVisor), as reported by the live result |
| Isolated business-tool executions | 48 |
| Isolated worker cleanup | Reported complete and verified by operator and host checks |
| Rejected compatibility patch | No patch in run, export returned HTTP 404 `artifact_not_found` |
| Public paid inference | Disabled |
| External acceptance | Pass |

The accepted release was **not** the latest GitHub source commit at verification
time. It was the specific server process revision observed at startup.
The external test pins that exact revision, checks that it is clean, and rejects
wrong or absent revisions.

## What happened during the real host migration

- The source DeepSeek agent passed 8/8 training cases.
- The unmodified Muse target passed 7/8 training cases.
- A generated tool-description candidate reached 8/8 on training.
- It passed only 7/8 on fresh validation, so Refit rejected it.
- The host generated no accepted compatibility patch for this failed attempt.
- The operator recorded 48 gVisor-contained tool executions and their cleanup.

This is **successful failure detection and safe rejection**, not a successful
repair for this particular on-host run.

## Other real repair evidence — distinct experiment

The earlier frozen patch has already passed independent external-runner
evaluations: patched Muse 24/24 vs unmodified Muse 13/24 across three seeds.
That evidence is separate from the on-host rejected run above; do not combine
the two experiments into a fictional successful on-host repair.

The previously pending frozen-patch report has now been recovered from the
Vultr host: source **8/8**, unmodified Muse **5/8**, patched Muse **8/8**, zero
unsafe attempts, **63** requests and **24** gVisor workers cleaned up. The
[original report, recovery checks and reproduction](vultr-frozen-patch-recovery-2026-11-06.md)
are preserved separately. Recovery made no new inference calls. This used the
previously exported patch, not the candidate rejected in the run above.

## Reproducing the public acceptance (no inference billing)

The checked-in smoke-test client reads complete bounded JSON responses
(up to 32 MiB) so the 48-worker report is not truncated:

```bash
python3 -m scripts.smoke_public \
  --url http://80.240.30.92 \
  --expected-revision e53feebd8f6d1d08595d23d3b0794aa814c60841 \
  --require-live-rejection \
  --output refit-external-acceptance.json
```

After a new deployment, substitute the **actual** intended deployed revision.
The command performs read-only HTTP requests. It does not start live jobs,
download credentials, or charge the inference account.

### Supporting links

- [Passing external acceptance](https://github.com/Davemafy/refit/actions/runs/42275235674)
- [GitHub-hosted gVisor verification](https://github.com/Davemafy/refit/actions/runs/42272418085)
- [Python integration and safety suite](https://github.com/Davemafy/refit/actions/runs/42275194211)
- [Full source](https://github.com/Davemafy/refit)

## Remaining acceptance boundaries

The public API remains deliberately read-only for paid operations and uses
HTTP without TLS. The reported gVisor worker containment applies to reviewed
synthetic workflows, not arbitrary third-party agent uploads. Public
authentication, encrypted transport, and general agent import are not
implemented. These must not be misrepresented in the submission.
