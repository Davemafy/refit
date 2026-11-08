"""Publish only independently verified, synthetic host-containment observations.

This runs as root in the authorized Vultr deployment after c1_acceptance.
The original complete receipt remains private; public JSON contains no paths,
host identifiers, request text, secrets or Docker daemon metadata.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from .c1_acceptance import independently_validate

REVISION = re.compile(r"[a-f0-9]{40}")
EXCEPTION = re.compile(r"[A-Za-z][A-Za-z0-9]{0,79}(?:Error|Exception)")


def sanitize(raw: dict, revision: str) -> dict:
    if not REVISION.fullmatch(revision):
        raise ValueError("Expected an exact 40-character deployed SHA")
    if not (raw.get("verified") is True and raw.get("host_canary_unchanged") is True
            and raw.get("prohibited_actions_observed") is True
            and raw.get("timeout_enforced") is True):
        raise ValueError("Containment acceptance has not passed")
    execution, timeout = raw.get("forbidden"), raw.get("timeout")
    if not isinstance(execution, dict) or not isinstance(timeout, dict):
        raise ValueError("Missing raw execution receipts")
    if not (independently_validate(execution) and
            independently_validate(timeout, synthetic_probe=False)):
        raise ValueError("Raw runtime, denial, timeout, or cleanup evidence is invalid")
    output = json.loads(execution["stdout"].strip())
    for key in ("host_canary_read", "outbound_network", "root_write"):
        if not isinstance(output[key], str) or not EXCEPTION.fullmatch(output[key]):
            raise ValueError("Only observed exception classes may be published")
    if output["host_key_env_present"] is not False:
        raise ValueError("Worker observed a forbidden credential")
    if output["host_canary_read"] != "FileNotFoundError":
        raise ValueError("Host-only canary was not denied")
    return {
        "kind": "controlled_vultr_host_containment_probe",
        "revision": revision,
        "recorded": True,
        "generated_by_model": False,
        "synthetic_data_only": True,
        "verified": True,
        "host_canary_unchanged": True,
        "attempts": [
            {"action": "read synthetic host-only canary",
             "observed": output["host_canary_read"], "blocked": True},
            {"action": "read Vultr inference credential environment",
             "observed": "absent", "blocked": True},
            {"action": "connect to external network",
             "observed": output["outbound_network"], "blocked": True},
            {"action": "write to read-only root filesystem",
             "observed": output["root_write"], "blocked": True},
            {"action": "exceed 2-second execution deadline",
             "observed": "timeout_enforced", "blocked": True},
        ],
        "workers": [
            {"kind": "denial_probe", "runtime": execution["runtime"],
             "status": execution["status"],
             "exit_code": execution.get("exit_code"),
             "container_created": execution["container_created"],
             "cleanup_verified": execution["container_removed_verified"],
             "ledger_valid": execution["ledger_valid"],
             "runtime_version": execution["runtime_identity"]["version"].splitlines()[0][:120]},
            {"kind": "timeout_probe", "runtime": timeout["runtime"],
             "status": timeout["status"],
             "timed_out": timeout["timed_out"],
             "container_created": timeout["container_created"],
             "cleanup_verified": timeout["container_removed_verified"],
             "ledger_valid": timeout["ledger_valid"],
             "runtime_version": timeout["runtime_identity"]["version"].splitlines()[0][:120]},
        ],
        "limitations": "Operator-generated synthetic containment proof; distinct from model-generated migration diagnostic.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    receipt = sanitize(json.loads(args.source.read_text(encoding="utf-8")), args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Host-root-owned and immutable to the non-root web process, even though
    # the latter must be able to read the sanitized proof.
    fd, tmp = tempfile.mkstemp(prefix=".c1-proof-", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, args.output)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(json.dumps({"published": True, "revision": args.revision,
                      "attempts": len(receipt["attempts"]), "verified": True}))


if __name__ == "__main__":
    main()
