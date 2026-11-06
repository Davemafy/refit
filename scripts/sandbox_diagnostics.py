"""Vultr model writes a diagnostic program, the sandbox executes it.

The protected host oracle (not the generated program) decides whether the
diagnosis matches observed migration evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .refit_vultr_probe import VultrInference, load_key
from .sandbox_runner import DockerSandbox


def diagnostics_input(record: dict) -> dict:
    if record.get("domain") not in ("refund", "deployment"):
        raise ValueError("unsupported migration domain")
    report = record.get("report")
    if not isinstance(report, dict):
        raise ValueError("migration has no report")
    phases = {}
    for name in ("source_training", "target_training",
                 "original_holdout", "repaired_holdout"):
        phase = report.get(name)
        if not isinstance(phase, dict):
            continue
        passed, total = phase.get("passed"), phase.get("total")
        if type(passed) is not int or type(total) is not int:
            raise ValueError("invalid phase score")
        if not 0 <= passed <= total <= 1000:
            raise ValueError("phase score out of bounds")
        failed = phase.get("failed", [])
        if not isinstance(failed, list) or not all(
                isinstance(item, str) and len(item) <= 100 for item in failed):
            raise ValueError("invalid failed-case list")
        phases[name] = {"passed": passed, "total": total, "failed": failed}
    if not all(key in phases for key in ("source_training", "target_training")):
        raise ValueError("source and target scores required")
    return {"domain": record["domain"], "phases": phases}


def expected_diagnostic(inputs: dict) -> dict:
    phases = inputs["phases"]
    source = phases["source_training"]["passed"]
    target = phases["target_training"]["passed"]
    before = phases.get("original_holdout")
    after = phases.get("repaired_holdout")
    return {
        "training_regression_delta": max(0, source - target),
        "target_failed_cases": sorted(set(phases["target_training"]["failed"])),
        "holdout_improvement": (
            after["passed"] - before["passed"]
            if before is not None and after is not None else None
        ),
    }


PROMPT = """You are a code-writing agent analyzing AI agent migration results.
Return ONLY executable Python 3.11 source; no code fences or explanations.
Your program reads JSON from /refit-input/input.json and computes exactly
one JSON object printed on stdout. Required fields:
training_regression_delta: max(0, source_training.passed - target_training.passed);
target_failed_cases: sorted unique target_training.failed strings;
holdout_improvement: repaired_holdout.passed - original_holdout.passed,
or null if either holdout phase is missing.
Input JSON schema: {"domain":"refund|deployment","phases":{phase_name:
{"passed":int,"total":int,"failed":[str]}}}.
Use actual JSON input, never hardcode counts or case names. Standard-library
imports only. No network, shell, filesystem mutations, credential access,
package installation or verifier modification. Output valid runnable Python.
"""


def extract_python(message: dict) -> str:
    code = message.get("content")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("model returned no code")
    code = code.strip()
    fence = chr(96) * 3
    if code.startswith(fence):
        lines = code.splitlines()
        if len(lines) < 3 or lines[-1] != fence:
            raise ValueError("malformed Python code fence")
        code = "\n".join(lines[1:-1])
    if "\x00" in code or len(code.encode("utf8")) > 20000:
        raise ValueError("generated source exceeds budget")
    return code


def generate_and_verify(record: dict, client, model: str,
                        sandbox: DockerSandbox) -> dict:
    inputs = diagnostics_input(record)
    response = client.complete(model, [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": json.dumps(inputs, sort_keys=True)},
    ], max_tokens=1600)
    code = extract_python(response)
    execution = sandbox.run(code, inputs, label="model_generated_diagnostic")
    observed = None
    error = None
    if (execution.get("status") == "passed" and execution.get("ledger_valid")
            and execution.get("container_removed_verified")):
        try:
            observed = json.loads(execution["stdout"].strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            error = "sandboxed program did not emit valid JSON"
    expected = expected_diagnostic(inputs)
    verified = isinstance(observed, dict) and observed == expected
    if observed is not None and not verified:
        error = "model-generated diagnosis does not match protected verifier"
    return {
        "kind": "vultr_model_generated_python_diagnostic",
        "generator_model": model,
        "source_domain": record["domain"],
        "generated_code": code,
        "expected": expected,
        "observed": observed,
        "verified": bool(verified),
        "validation_error": error,
        "sandbox": execution,
        "limitations": (
            "Supplementary migration diagnosis, not business acceptance. "
            "Existing business tests use synthetic state."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recorded", choices=("refund", "deployment"),
                        default="refund")
    parser.add_argument("--model", choices=("deepseek-v4.1-flash-1017",
                        "muse-glimmer-30b", "raon-1-mini-preview"),
                        default="deepseek-v4.1-flash-1017")
    parser.add_argument("--runtime", choices=("runc", "runsc"), default="runc")
    parser.add_argument("--env-file", type=Path,
                        default=Path("/etc/refit/inference.env"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = (Path(__file__).resolve().parent.parent / "data" / "recorded" /
            f"{args.recorded}-2026-11-06.json")
    record = json.loads(path.read_text(encoding="utf8"))
    client = VultrInference(load_key(args.env_file), max_requests=1)
    result = generate_and_verify(record, client, args.model,
                                 DockerSandbox(runtime=args.runtime))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "verified": result["verified"],
        "model_requests": client.requests,
        "generator_model": args.model,
        "execution_status": result["sandbox"]["status"],
        "container_removed_verified": result["sandbox"]["container_removed_verified"],
        "diagnostic": result["observed"],
        "validation_error": result["validation_error"],
        "report_path": str(args.output) if args.output else None,
    }, indent=2))
    if not result["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
