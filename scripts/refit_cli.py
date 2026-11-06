"""Refit CLI for locally trusted agent adapters.

Usage:
    python -m scripts.refit_cli --domain refund --source ... --target ...

Adapter protocol:
    CONTRACT: AgentContract
    run_live(client, source, target, repair_model, seed) -> result

This CLI imports locally trusted Python modules. It does not sandbox their
code. Never expose --adapter as a public server argument.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import secrets

from .refit_vultr_probe import VultrInference, load_key

BUILTINS = {
    "refund": "scripts.refund_adapter",
    "deployment": "scripts.deployment_incident_probe",
}


def resolve_adapter(domain: str, adapter_path: str | None):
    if adapter_path:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", adapter_path):
            raise ValueError("invalid Python adapter module path")
        module = importlib.import_module(adapter_path)
    else:
        module = importlib.import_module(BUILTINS[domain])
    if not callable(getattr(module, "run_live", None)):
        raise ValueError("adapter must export callable run_live")
    contract = getattr(module, "CONTRACT", None)
    if not getattr(contract, "name", None) or not callable(getattr(contract, "schemas", None)):
        raise ValueError("adapter must export a valid CONTRACT")
    return module


def summarize(report: dict, requests: int, output: Path):
    return {
        "status": report["status"],
        "contract": report.get("contract"),
        "source_training": report.get("source_training"),
        "target_training": report.get("target_training"),
        "regressions": report.get("regressions"),
        "selected_variant": report.get("selected_variant"),
        "validation": report.get("validation"),
        "original_holdout": report.get("original_holdout"),
        "repaired_holdout": report.get("repaired_holdout"),
        "model_requests": requests,
        "report_path": str(output),
    }


def main():
    p = argparse.ArgumentParser(
        description="Refit: detect, adapt and verify a model migration for a supported agent"
    )
    p.add_argument("--domain", choices=tuple(BUILTINS), default="refund")
    p.add_argument("--adapter", help="Locally trusted Python module implementing Refit's adapter protocol")
    p.add_argument("--source", default="deepseek-v4.1-flash-1017")
    p.add_argument("--target", default="muse-glimmer-30b")
    p.add_argument("--repair", default="deepseek-v4.1-flash-1017")
    p.add_argument("--seed", type=int)
    p.add_argument("--max-requests", type=int, default=160)
    p.add_argument("--env-file", type=Path, default=Path("/etc/refit/inference.env"))
    p.add_argument("--output", type=Path, default=Path("refit-migration-report.json"))
    args = p.parse_args()
    if not 1 <= args.max_requests <= 200:
        p.error("--max-requests must be between 1 and 200")
    if args.source == args.target:
        p.error("--source and --target must differ")
    # Import adapter before loading any sensitive credential. This supports
    # trusted local code only, never unreviewed internet downloads.
    adapter = resolve_adapter(args.domain, args.adapter)
    key = load_key(args.env_file)
    client = VultrInference(key, max_requests=args.max_requests)
    seed = args.seed if args.seed is not None else secrets.randbelow(2147483647)
    try:
        report = adapter.run_live(client, args.source, args.target, args.repair, seed)
    except Exception as exc:
        report = {"status": "execution_error", "error": f"{type(exc).__name__}: {str(exc)[:450]}"}
    record = {
        "contract": adapter.CONTRACT.name,
        "source": args.source,
        "target": args.target,
        "repair_model": args.repair,
        "seed": seed,
        "model_requests": client.requests,
        "report": report,
    }
    previous = os.umask(0o077)
    try:
        args.output.write_text(json.dumps(record, indent=2), encoding="utf8")
    finally:
        os.umask(previous)
    print(json.dumps(summarize(report, client.requests, args.output), indent=2))


if __name__ == "__main__":
    main()
