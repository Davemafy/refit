# Paired deployment evaluation — November 6, 2026

Result: **compatible_on_sample**, not a repair demonstration.

[Live GitHub Actions execution](https://github.com/Davemafy/refit/actions/runs/42254485740)
used commit `a6cf1e35c16ff79637a646babf7637677b9b8c6c`, evaluation version 2,
seed `61062731` and 186 real Vultr inference requests within a 320-request cap.
The source was `deepseek-v4.1-flash-1017`; the target was `muse-glimmer-30b`.

| Split | Source | Unchanged target | Unsafe attempts |
| --- | --- | --- | --- |
| Training | 8/8 | 8/8 | 0 for both |
| Validation | 8/8 | 8/8 | 0 for both |
| Holdout | 8/8 | 8/8 | 0 for both |

No regression was observed, no optimizer was called, and no patch was exported.
This is one seed over eight known synthetic deployment workflow families with
fresh state identifiers. It does not establish general reliability or demonstrate
repair transfer. Business tools ran in process on the GitHub runner; this is not
Vultr VM sandbox deployment evidence.

The full report, including successful and unsuccessful tool transitions, final
responses and source comparisons, is preserved in
[`data/evaluations/paired-deployment-2026-11-06.json.gz`](../data/evaluations/paired-deployment-2026-11-06.json.gz).
Read it without installing dependencies:

```bash
python3 - <<'PY'
import gzip, json
with gzip.open('data/evaluations/paired-deployment-2026-11-06.json.gz', 'rt') as stream:
    record = json.load(stream)
print(record['report']['status'], record['model_requests'])
PY
```

The live configuration was disabled immediately after submitting the one-shot
run. Subsequent pushes do not authorize repeat inference charges.
