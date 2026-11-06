"""Sandbox-side gateway for one trusted built-in Refit agent scenario."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def run(domain: str, phase: str, seed: int, case_index: int) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import refund_adapter, deployment_incident_probe
    modules = {"refund": refund_adapter, "deployment": deployment_incident_probe}
    if domain not in modules or phase not in ("train", "validation", "holdout"):
        raise ValueError("invalid domain or phase")
    if not 0 <= seed < 2_147_483_647 or not 0 <= case_index < 16:
        raise ValueError("invalid scenario")
    cases = modules[domain].make_cases(seed, phase)
    if case_index >= len(cases):
        raise ValueError("case index too large")
    env = cases[case_index].environment()
    try:
        calls = 0
        for raw in sys.stdin.buffer:
            if len(raw) > 32768:
                break
            request = {}
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("expected JSON object")
                op = request.get("op")
                if op == "call":
                    if calls >= 40:
                        raise ValueError("tool-call budget exceeded")
                    calls += 1
                    name = request.get("tool")
                    if not isinstance(name, str) or len(name) > 100:
                        raise ValueError("invalid tool name")
                    result = {"result": env.call(name, request.get("arguments"))}
                elif op == "verify":
                    result = {"verdict": env.verify(), "events": env.events}
                elif op == "close":
                    result = {"closed": True}
                else:
                    raise ValueError("unsupported operation")
            except (ValueError, TypeError, KeyError) as exc:
                result = {"error": type(exc).__name__}
            sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
            sys.stdout.flush()
            if request.get("op") == "close":
                break
    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--domain", choices=("refund", "deployment"), required=True)
    p.add_argument("--phase", choices=("train", "validation", "holdout"), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--case-index", type=int, required=True)
    args = p.parse_args()
    run(args.domain, args.phase, args.seed, args.case_index)


if __name__ == "__main__":
    main()
