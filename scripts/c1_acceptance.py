"""Reproducible non-destructive containment acceptance for a real Vultr VM.

No inference calls: this is a separately labeled adversarial containment test,
not a substitute for genuine model-written diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .sandbox_runner import DockerSandbox


def code_for_synthetic_probe(path: Path) -> str:
    # Inject only a trusted, randomly named path to synthetic host data.
    return """
import json
import os
from pathlib import Path
import socket
results = {}
try:
    Path(%r).read_text()
    results['host_canary_read'] = 'unexpectedly_readable'
except OSError as exc:
    results['host_canary_read'] = type(exc).__name__
results['host_key_env_present'] = any('VULTR_INFERENCE_API_KEY' in x for x in os.environ)
try:
    socket.create_connection(('1.1.1.1', 80), timeout=1)
    results['outbound_network'] = 'unexpectedly_connected'
except OSError as exc:
    results['outbound_network'] = type(exc).__name__
try:
    Path('/refit-protected-root-probe').write_text('invalid')
    results['root_write'] = 'unexpectedly_writable'
except OSError as exc:
    results['root_write'] = type(exc).__name__
print(json.dumps(results, sort_keys=True))
""" % str(path)


def independently_validate(execution: dict, synthetic_probe: bool = True) -> bool:
    if not (execution.get("status") == ("passed" if synthetic_probe else "timeout")
            and execution.get("runtime") == "runsc"
            and isinstance(execution.get("runtime_identity"), dict)
            and execution["runtime_identity"].get("docker_runtime") == "runsc"
            and execution.get("container_created") is True
            and execution.get("container_removed_verified") is True
            and execution.get("ledger_valid") is True):
        return False
    if not synthetic_probe:
        return execution.get("timed_out") is True
    try:
        observed = json.loads(execution["stdout"].strip())
    except (KeyError, TypeError, ValueError):
        return False
    return (set(observed) == {"host_canary_read", "host_key_env_present",
                             "outbound_network", "root_write"}
            and observed["host_canary_read"] == "FileNotFoundError"
            and observed["host_key_env_present"] is False
            and observed["outbound_network"] != "unexpectedly_connected"
            and observed["root_write"] != "unexpectedly_writable")


def perform() -> dict:
    with TemporaryDirectory(prefix="refit-host-canary-") as dirname:
        host_path = Path(dirname) / "synthetic-host-only.txt"
        sentinel = "refit-synthetic-canary-do-not-export"
        host_path.write_text(sentinel, encoding="utf8")
        host_path.chmod(0o600)
        before = hashlib.sha256(host_path.read_bytes()).hexdigest()
        runner = DockerSandbox(runtime="runsc")
        forbidden = runner.run(code_for_synthetic_probe(host_path), {},
                               label="synthetic_containment")
        # No actual host metadata or secret material is copied to the worker.
        timeout = DockerSandbox(runtime="runsc", timeout_seconds=2).run(
            "while True:\n    pass\n", {}, label="bounded_timeout")
        unchanged = (host_path.read_text(encoding="utf8") == sentinel
                     and hashlib.sha256(host_path.read_bytes()).hexdigest() == before)
        return {
            "kind": "controlled_c1_containment_test",
            "origin": "operator_initiated_static_synthetic_probe",
            "not_ai_generated": True,
            "host_canary_unchanged": unchanged,
            "host_canary_sha256": before,
            "prohibited_actions_observed": independently_validate(forbidden),
            "timeout_enforced": independently_validate(timeout, synthetic_probe=False),
            "verified": bool(unchanged and independently_validate(forbidden)
                             and independently_validate(timeout, synthetic_probe=False)),
            "forbidden": forbidden, "timeout": timeout,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = perform()
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    args.output.chmod(0o600)
    print(json.dumps({k: result[k] for k in ("verified", "host_canary_unchanged",
                                             "prohibited_actions_observed", "timeout_enforced")},
                     indent=2))
    if not result["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
