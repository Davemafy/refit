# Frozen patch verified on Vultr

The previously pending report was recovered from the actual Vultr host through
an authorized SSH session. Its original execution completed on November 6,
2026 at approximately 18:44 UTC. Recovery made **zero additional inference
requests** and did not change the deployed application.

## Measured result

| Evaluation | Passed | Unsafe attempts |
| --- | ---: | ---: |
| DeepSeek source | 8/8 | 0 |
| Unmodified Muse | 5/8 | 0 |
| Muse with the unchanged archived patch | 8/8 | 0 |

- Verdict: `frozen_patch_passed_sample`.
- Predeclared holdout seed: `605120371`.
- Actual inference requests: **63**, reconciled as 23 source + 17 original
  target + 23 patched target.
- Tool execution: **24 disposable gVisor (`runsc`) workers**, all with verified
  cleanup receipts. A fresh recovery-time check found no remaining Refit
  containers and confirmed the same healthy Docker daemon identity.
- Engine release: `e53feebd8f6d1d08595d23d3b0794aa814c60841`, recorded clean.
- The unchanged patch is available from the
  [public artifact endpoint](http://80.240.30.92/api/runs/recorded-refund-2026-11-06/artifact).

This is a fixed-patch verification on known refund holdout families. The patch
was generated and exported earlier; this test did not generate a new patch or
certify unseen workflow families.

## Preserved evidence

The [compressed recovery bundle](../data/evaluations/vultr-host-frozen-recovered-2026-11-06.json.gz)
contains the original report and operator wrapper, execution log, safe/hostile
probe reports, recomputable event ledgers, cleanup rechecks, image identity,
and the recovery manifest. It also retains the initial permission-denied probe
that led to the operator-umask fix; it is not relabeled as a passing probe.

Original report SHA-256:

```text
9a993fb72548a0324556531230ea22fc01d630abeead793e988d4800c841cf4b
```

Patch digest, including its integrity field:

```text
sha256:5c80c12561e12cb8cc3940c6eb5ca82460fa12e1a39a7cfb96f8717f390f6505
```

The raw report omitted a `runner` field. Its preserved operator wrapper directly
uses the native `VultrInference` client, `verify_frozen`, and `sandbox_cases`.
Validation explicitly supplies `runner="native"` in memory and records that
normalization. **The original report bytes are preserved unchanged.** The
validator also checked nonempty phases, case counts, scores, request totals,
patch identity and expected seed. Safe/hostile probe ledger and code hashes
were independently recomputed.

`tests/test_refit_host_evidence.py` runs in ordinary CI discovery on Python
3.11 and 3.12 without Docker, network access, or inference. It checks pinned
raw-report and wrapper hashes, every archived file hash, the unchanged patch,
nonempty paired cases, reconciled scores and request totals, all 24 worker
cleanup receipts, and the safe/hostile probe ledgers. These checks validate the
preserved records; they do not turn those records into signed host attestation.

Reproduce the report validation offline from this checkout:

```python
import gzip
import hashlib
import json
from pathlib import Path
from scripts import refund_adapter
from scripts.recover_frozen_evidence import validate_report

bundle = json.loads(gzip.decompress(Path(
    "data/evaluations/vultr-host-frozen-recovered-2026-11-06.json.gz"
).read_bytes()))
raw = bundle["files"]["frozen-verification.json"].encode()
assert hashlib.sha256(raw).hexdigest() == bundle["manifest"]["raw_report_sha256"]
record = json.loads(raw)
assert "runner" not in record
for trial in record["report"]["trials"]:
    for result in trial["evaluations"].values():
        assert result["total"] > 0
        assert len(result["cases"]) == result["total"]
summary = validate_report(
    dict(record, runner="native"), record["artifact"], refund_adapter,
    expected_seed=605120371,
)
assert summary["status"] == "verified"
print(summary)
```

The report was recovered from the named VPS, and its records identify the
engine revision. These observations and integrity hashes are not signed host
attestation or an independent audit of the original inference calls.

## Keep the experiments distinct

1. The original automatic on-host repair search, `live-8faad4e25db3a36d`,
   **rejected** its newly generated candidate at validation. It used 133 model
   requests and 48 workers; its patch remains withheld.
2. This separate frozen-patch test **passed** using the earlier, unchanged
   exported patch. It used 63 model requests and 24 workers.
3. The separate upstream tau2 runner experiment remains 24/24 patched versus
   13/24 unmodified across three seeds.

The [fresh external public check](../data/evaluations/vultr-public-smoke-recovery-2026-11-06.json)
confirms the deployed release, downloadable archived patch, published rejection,
and disabled public execution. The recovered frozen report is published here
as an evidence bundle; it is not inserted into the API as a newly generated
successful migration.
