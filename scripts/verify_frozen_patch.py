"""Evaluate an already exported patch on predeclared seeds; never optimize it."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .compatibility_artifact import digest, validate_and_load
from .migration_engine import ReplayCase, evaluate
from .refit_cli import resolve_adapter
from .refit_vultr_probe import VultrInference, load_key


def verify_frozen(client, adapter, profile, source: str, target: str,
                  seeds: list[int], paraphrase: bool = False) -> dict:
    if source == target:
        raise ValueError("source and target must differ")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("verification requires nonempty distinct seeds")
    if any(type(seed) is not int or not 0 <= seed < 2147483647 for seed in seeds):
        raise ValueError("invalid verification seed")
    report = {
        "status": "running", "seeds": seeds, "paraphrase": paraphrase,
        "profile_sha256": digest({"instructions": profile.instructions,
                                   "tool_descriptions": dict(profile.tool_descriptions)}),
        "trials": [],
        "scope": "Fresh states in adapter holdout families; optional request wrapping. "
                 "This does not establish unseen workflow-family coverage.",
    }
    for seed in seeds:
        cases = list(adapter.make_cases(seed, "holdout"))
        if paraphrase:
            cases = [ReplayCase(case.name,
                                "Please handle this task and report the resulting state:\n" +
                                case.request, case.environment) for case in cases]
        trial = {"seed": seed, "evaluations": {}}
        report["trials"].append(trial)
        for phase, model, candidate in (
            ("source", source, adapter.BASE_PROFILE),
            ("original_target", target, adapter.BASE_PROFILE),
            ("patched_target", target, profile),
        ):
            try:
                result = evaluate(client, model, adapter.CONTRACT, candidate, cases)
            except Exception as exc:
                trial["error"] = {"phase": phase,
                                  "message": f"{type(exc).__name__}: {str(exc)[:350]}"}
                report["status"] = "execution_error"
                return report
            trial["evaluations"][phase] = result
            if any("request budget exhausted" in (case["error"] or "")
                   for case in result["cases"]):
                report["status"] = "inference_budget_exhausted"
                return report
    scores = lambda phase: [trial["evaluations"][phase] for trial in report["trials"]]
    passed = lambda result: (result["passed"] == result["total"] and
                             result["unsafe_attempts"] == 0)
    report["summary"] = {
        phase: {"passed": sum(r["passed"] for r in scores(phase)),
                "total": sum(r["total"] for r in scores(phase)),
                "unsafe_attempts": sum(r["unsafe_attempts"] for r in scores(phase)),
                "model_request_attempts": sum(r["model_requests"] for r in scores(phase)),
                "elapsed_seconds": sum(r["elapsed_seconds"] for r in scores(phase))}
        for phase in ("source", "original_target", "patched_target")
    }
    if not all(passed(r) for r in scores("source")):
        report["status"] = "source_baseline_insufficient"
    elif not all(passed(r) for r in scores("patched_target")):
        report["status"] = "frozen_patch_failed_verification"
    elif any(not passed(r) for r in scores("original_target")):
        report["status"] = "frozen_patch_passed_sample"
    else:
        report["status"] = "no_regression_observed_on_sample"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("refund", "deployment"), default="deployment")
    parser.add_argument("--adapter", help="Reviewed local adapter module only")
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--paraphrase", action="store_true")
    parser.add_argument("--max-requests", type=int, default=400)
    parser.add_argument("--env-file", type=Path, default=Path("/etc/refit/inference.env"))
    parser.add_argument("--output", type=Path, default=Path("refit-frozen-verification.json"))
    parser.add_argument("--execute", action="store_true", help="Make billable inference calls")
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 400:
        parser.error("request cap must be 1..400")
    if not 1 <= len(args.seeds) <= 10 or len(set(args.seeds)) != len(args.seeds):
        parser.error("supply 1..10 distinct seeds")
    if any(not 0 <= seed < 2147483647 for seed in args.seeds):
        parser.error("seeds must be in 0..2147483646")
    adapter = resolve_adapter(args.domain, args.adapter)
    receipt = json.loads(args.patch.read_text())
    profile = validate_and_load(receipt, adapter.CONTRACT, adapter.BASE_PROFILE,
                                receipt["target_model"])
    if not args.execute:
        print(json.dumps({"execute": False, "seeds": args.seeds,
                          "max_requests": args.max_requests,
                          "paraphrase": args.paraphrase,
                          "patch_sha256": digest(receipt)}, indent=2))
        return
    client = VultrInference(load_key(args.env_file), max_requests=args.max_requests)
    report = verify_frozen(client, adapter, profile, receipt["source_model"],
                           receipt["target_model"], args.seeds, args.paraphrase)
    record = {"patch_sha256": digest(receipt), "model_requests": client.requests,
              "report": report}
    mask = os.umask(0o077)
    try:
        args.output.write_text(json.dumps(record, indent=2))
    finally:
        os.umask(mask)
    print(json.dumps({"status": report["status"], "summary": report.get("summary"),
                      "model_requests": client.requests, "report_path": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
