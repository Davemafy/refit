"""One-shot paid Vultr TypeScript migration acceptance on an external gVisor runner.

This does not modify production. It uses the original pinned AI SDK 7 source
and independent train/validation/holdout cases. It records failure honestly.
All requests are capped, and no provider key or raw source enters the receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from .application_import import source_snapshot
from .application_run import MODELS, configuration, run_migration, RunStopped
from .refit_vultr_probe import VultrInference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="refit-application")
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    if set(request) != {"run_live", "source", "target", "max_requests"}:
        parser.error("Request must contain only run_live, source, target and max_requests.")
    if request["run_live"] is not True:
        print("Live TypeScript acceptance disabled by request file.")
        return 0
    source, target, ceiling = (request[k] for k in ("source", "target", "max_requests"))
    if source not in MODELS or target not in MODELS or source == target or (
            type(ceiling) is not int or not 14 <= ceiling <= 48):
        parser.error("Choose two supported distinct models and at most 48 requests.")
    key = os.environ.get("VULTR_INFERENCE_API_KEY", "")
    if not key:
        parser.error("Missing VULTR_INFERENCE_API_KEY. No inference was attempted.")
    setup_data = json.loads(args.setup.read_text())
    for case in setup_data["cases"]:
        match = re.search(r"(order|invoice|receipt)\.txt", case["prompt"])
        if not match:
            parser.error("Expected a pinned original read-only fixture.")
        case["state"] = [
            {"path": "records/" + match.group(0), "op": "unchanged"},
            {"path": "records/unexpected.txt", "op": "absent"},
        ]
    snapshot = source_snapshot(args.archive.read_bytes())
    setup = configuration(snapshot, setup_data)
    if snapshot["discovery"]["runtime"] != "typescript":
        parser.error("Pinned snapshot did not detect the original TypeScript agent.")
    broker = VultrInference(key, max_requests=ceiling)
    events = []
    result = None
    error = None
    try:
        result = run_migration(snapshot, setup, source, target, args.image, broker,
                               lambda name, value: events.append((name, value)), lambda: False)
    except (RunStopped, RuntimeError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"[:240]
    cleanups = [row["receipt"].get("verified", False) for name, row in events
                if name == "sandbox_cleanup"]
    cases = [
        {"name": row["case"], "phase": row["phase"], "model": row["model"],
         "passed": row["passed"], "error": row.get("error"),
         "model_requests": row.get("model_requests"),
         "repeated_read_only_calls": row.get("repeated_read_only_calls"),
         "tool_observed": row["verdict"].get("required_tool_observed"),
         "state_checks_passed": row["verdict"].get("state_checks_passed")}
        for name, row in events if name == "case_completed"
    ]
    repeats = [
        {"model": row["model"], "case": row["case"], "consecutive": row["consecutive"]}
        for name, row in events if name == "repeated_read_only_tool_calls"
    ]
    status = result["status"] if result else "execution_stopped"
    export = bool(result and result.get("export"))
    receipt = {
        "kind": "external_paid_vultr_original_typescript_agent",
        "production_deployment": False,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source": source, "target": target, "request_ceiling": ceiling,
        "vultr_attempts": broker.requests, "status": status,
        "export_available": export,
        "fresh_export_verification_count": len(result.get("verification", [])) if result else 0,
        "case_evidence": cases,
        "cleanup_receipts": len(cleanups), "cleanup_verified": all(cleanups) and len(cleanups) > 0,
        "repeated_read_only_call_warnings": repeats,
        "error": error,
        "honest_limitations": (
            "AI SDK 7 pinned upstream agent, curated Node runtime, independent three-case fixture. "
            "Not arbitrary TypeScript service or general repair verification."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("case_evidence", "honest_limitations")}))
    return 0 if export and receipt["cleanup_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
