"""Read-only recovery of a completed frozen-patch report on the Vultr host.

Never invokes a model, reads an inference credential, or invents a passing trial.
Only a verified, previously written report can produce the "verified" status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from .compatibility_artifact import digest, validate_and_load
from .refit_cli import BUILTINS, resolve_adapter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATCH = ROOT / "data/recorded/refund-compatibility-2026-11-06.artifact.json"
SEARCH_ROOTS = (
    Path("/opt/refit-app"),
    Path("/opt/refit"),
    Path("/var/lib/refit/evidence"),
)
SEARCH_NAMES = ("refit-frozen-verification.json", "*frozen*verification*.json")
MAX_REPORT_BYTES = 32 * 1024 * 1024
PHASES = ("source", "original_target", "patched_target")
VALID_STATUSES = {
    "frozen_patch_passed_sample",
    "frozen_patch_failed_verification",
    "source_baseline_insufficient",
    "no_regression_observed_on_sample",
    "inference_budget_exhausted",
    "execution_error",
    "upstream_fixture_failed",
}


def candidates(roots=SEARCH_ROOTS) -> list[Path]:
    """Search only frozen-verification filenames, not arbitrary host files."""
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for name in SEARCH_NAMES:
            for pattern in (name, "*/" + name, "*/*/" + name):
                for path in root.glob(pattern):
                    if path.is_file() and not path.is_symlink():
                        found[str(path)] = path
    return sorted(found.values(), key=lambda p: str(p))


def read_report(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Verification report must be an existing regular file")
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("Verification report exceeds 32 MiB")
    data = path.read_bytes()
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError("Verification report exceeds 32 MiB")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("Verification record is not an object")
    return parsed, hashlib.sha256(data).hexdigest()


def integer(value: object) -> bool:
    return type(value) is int and value >= 0


def validate_report(record: dict, receipt: dict, adapter, *,
                    expected_seed: int | None = None) -> dict:
    """Check patch binding, every reported trial and claimed aggregate totals."""
    patch_digest = digest(receipt)
    if record.get("patch_sha256") != patch_digest:
        raise ValueError("Frozen report belongs to a different patch")
    if record.get("runner") not in ("native", "tau2"):
        raise ValueError("Unknown runner in verification receipt")
    calls = record.get("model_requests")
    if not integer(calls) or calls > 400:
        raise ValueError("Invalid model request count")
    report = record.get("report")
    if not isinstance(report, dict) or report.get("status") not in VALID_STATUSES:
        raise ValueError("Missing or unknown frozen verification status")
    seeds = report.get("seeds")
    if (not isinstance(seeds, list) or not seeds
            or any(type(seed) is not int or seed < 0 or seed >= 2147483647 for seed in seeds)
            or len(seeds) != len(set(seeds))):
        raise ValueError("Verification seeds missing, duplicated or invalid")
    if expected_seed is not None and expected_seed not in seeds:
        raise ValueError("Predeclared expected seed not present in report")
    profile = validate_and_load(receipt, adapter.CONTRACT, adapter.BASE_PROFILE,
                                receipt["target_model"])
    expected_profile = digest({"instructions": profile.instructions,
                               "tool_descriptions": dict(profile.tool_descriptions)})
    if report.get("profile_sha256") != expected_profile:
        raise ValueError("Frozen report profile does not match archived patch")
    trials = report.get("trials")
    if not isinstance(trials, list) or len(trials) > len(seeds):
        raise ValueError("Malformed frozen verification trials")
    totals = {p: {"passed": 0, "total": 0, "unsafe_attempts": 0,
                  "model_request_attempts": 0} for p in PHASES}
    observed_seeds = []
    for trial in trials:
        if not isinstance(trial, dict) or trial.get("seed") not in seeds:
            raise ValueError("Trial refers to invalid seed")
        if trial["seed"] in observed_seeds:
            raise ValueError("Duplicate trial seed")
        observed_seeds.append(trial["seed"])
        evaluations = trial.get("evaluations")
        if not isinstance(evaluations, dict) or set(evaluations) - set(PHASES):
            raise ValueError("Malformed evaluation phases")
        for phase, result in evaluations.items():
            if not isinstance(result, dict):
                raise ValueError("Malformed phase result")
            passed, total, unsafe = (
                result.get("passed"), result.get("total"), result.get("unsafe_attempts"))
            requests = result.get("model_requests")
            if (not all(integer(x) for x in (passed, total, unsafe, requests))
                    or passed > total):
                raise ValueError("Invalid per-trial results")
            for key, amount in (("passed", passed), ("total", total),
                                ("unsafe_attempts", unsafe),
                                ("model_request_attempts", requests)):
                totals[phase][key] += amount
    success = report["status"] == "frozen_patch_passed_sample"
    if success:
        if len(trials) != len(seeds) or set(observed_seeds) != set(seeds):
            raise ValueError("Passing receipt omits predeclared trials")
        if calls <= 0:
            raise ValueError("Passing receipt reports zero inference calls")
        for trial in trials:
            if trial.get("error") or set(trial["evaluations"]) != set(PHASES):
                raise ValueError("Passing receipt has an error or incomplete phase")
            for phase in ("source", "patched_target"):
                r = trial["evaluations"][phase]
                if r["passed"] != r["total"] or r["unsafe_attempts"]:
                    raise ValueError("Passing receipt contradicts phase evidence")
        if not any(trial["evaluations"]["original_target"]["passed"]
                   < trial["evaluations"]["original_target"]["total"]
                   for trial in trials):
            raise ValueError("Passing receipt has no observed target regression")
    if success:
        # The client records every billable request. Match the three frozen
        # phases, plus the optional upstream tau2 mock-domain fixture calls.
        # Incomplete/error reports can have failed attempts that never reached
        # an evaluation result, so do not impose this equality on failures.
        counted_requests = sum(totals[p]["model_request_attempts"] for p in PHASES)
        fixtures = record.get("upstream_fixtures")
        if fixtures is not None:
            if record["runner"] != "tau2" or not isinstance(fixtures, dict):
                raise ValueError("Upstream fixture evidence requires the tau2 runner")
            for name in ("source", "target"):
                outcome = fixtures.get(name)
                if not isinstance(outcome, dict) or not integer(outcome.get("model_requests")):
                    raise ValueError("Missing fixture request counts")
                counted_requests += outcome["model_requests"]
        if calls != counted_requests:
            raise ValueError("Overall model requests do not reconcile with trial evidence")
    summaries = report.get("summary")
    if success and not isinstance(summaries, dict):
        raise ValueError("Passing receipt has no aggregate scores")
    if isinstance(summaries, dict):
        for phase, counts in totals.items():
            aggregate = summaries.get(phase)
            if not isinstance(aggregate, dict):
                raise ValueError("Missing aggregate phase")
            if any(aggregate.get(key) != amount for key, amount in counts.items()):
                raise ValueError("Aggregate scores differ from individual trials")
    return {
        "status": "verified" if success else "observed_not_passed",
        "verdict": report["status"],
        "runner": record["runner"],
        "source_model": receipt["source_model"],
        "target_model": receipt["target_model"],
        "patch_sha256": patch_digest,
        "seeds": seeds,
        "observed_trials": len(trials),
        "model_requests": calls,
        "scores": {p: {"passed": x["passed"], "total": x["total"],
                       "unsafe_attempts": x["unsafe_attempts"]}
                   for p, x in totals.items()},
        "scope": "Known holdout families only; this does not certify unseen workflows.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        help="Existing on-host frozen report; do not launch inference")
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH)
    parser.add_argument("--domain", choices=tuple(BUILTINS), default="refund")
    parser.add_argument("--expected-seed", type=int)
    parser.add_argument("--output", type=Path,
                        help="Optional sanitized JSON summary, not a raw model transcript")
    args = parser.parse_args()
    if args.expected_seed is not None and not 0 <= args.expected_seed < 2147483647:
        parser.error("expected seed must be in range")
    paths = [args.report] if args.report else candidates()
    if not paths:
        print(json.dumps({"status": "not_found", "message":
                          "No existing frozen verification report found. "
                          "No inference was run."}, indent=2))
        return 3
    adapter = resolve_adapter(args.domain, None)
    receipt = json.loads(args.patch.read_text(encoding="utf8"))
    accepted = []
    failures = []
    for path in paths:
        try:
            record, sha = read_report(path)
            summary = validate_report(record, receipt, adapter,
                                      expected_seed=args.expected_seed)
            summary["report_file_sha256"] = sha
            summary["source_filename"] = path.name
            accepted.append(summary)
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({"filename": path.name, "reason": type(error).__name__})
    # Do not let a failed receipt mask a completed passing one, and do not
    # silently treat a malformed file as a passing evaluation.
    if not accepted:
        print(json.dumps({"status": "no_valid_report", "invalid_candidates": failures,
                          "no_inference_run": True}, indent=2))
        return 2
    result = {"status": "recovered", "no_inference_run": True,
              "reports": accepted, "invalid_candidates": failures}
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output is not None:
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
