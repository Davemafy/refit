"""Versioned, reviewable Refit compatibility artifact.

A patch is deployable configuration for an integrating agent, NOT executable
Python, and NOT a permission to bypass the originating business policy.
The digest detects accidental changes; it is not a cryptographic signature.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from .migration_engine import AgentContract, AgentProfile

FORMAT_VERSION = "refit.compatibility.v1"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def contract_details(contract: AgentContract) -> dict:
    return {"name": contract.name, "tools": contract.tools,
            "protected_invariants": contract.policies}


def profile_details(profile: AgentProfile) -> dict:
    return {"instructions": profile.instructions,
            "tool_descriptions": dict(profile.tool_descriptions)}


def create_receipt(report: dict, contract: AgentContract, baseline: AgentProfile,
                   source_model: str, target_model: str) -> dict:
    if report.get("status") != "verified_adaptation":
        raise ValueError("only independently verified adaptations can be exported")
    needed = ("source_training", "target_training", "validation",
              "original_holdout", "repaired_holdout", "accepted_patch")
    if any(x not in report for x in needed):
        raise ValueError("missing evidence required for verified adaptation")
    checks = (report["source_training"], report["validation"],
              report["repaired_holdout"])
    if any(x["passed"] != x["total"] or x.get("unsafe_attempts") for x in checks):
        raise ValueError("acceptance gates not satisfied")
    if report["repaired_holdout"]["passed"] <= report["original_holdout"]["passed"]:
        raise ValueError("no observed holdout improvement")
    patch = report["accepted_patch"]
    if set(patch) != {"type", "instructions", "tool_descriptions"}:
        raise ValueError("unrecognized accepted patch structure")
    instruction = patch["instructions"]
    descriptions = patch["tool_descriptions"]
    if not isinstance(instruction, str) or not 30 <= len(instruction) <= 5000:
        raise ValueError("unsafe instructions field")
    if (not isinstance(descriptions, dict) or
            not set(descriptions).issubset(contract.tool_names()) or
            any(not isinstance(v, str) or not 10 <= len(v) <= 2000
                for v in descriptions.values())):
        raise ValueError("invalid tool description patch")
    body = {
        "format": FORMAT_VERSION,
        "contract": contract.name,
        "source_model": source_model,
        "target_model": target_model,
        "source_contract_sha256": digest(contract_details(contract)),
        "source_profile_sha256": digest(profile_details(baseline)),
        "patch_type": patch["type"],
        "target_profile": {"instructions": instruction,
                           "tool_descriptions": descriptions},
        "evidence": {
            "source_training": report["source_training"],
            "target_training": report["target_training"],
            "validation": report["validation"],
            "original_holdout": report["original_holdout"],
            "repaired_holdout": report["repaired_holdout"],
        },
        "caveat": (
            "Success is empirical for the stated task distribution, not a "
            "guarantee of future agent reliability. Customer must review the "
            "patch and control rollout."
        ),
    }
    return {**body, "integrity_sha256": digest(body)}


def validate_and_load(receipt: dict, contract: AgentContract,
                      baseline: AgentProfile, target_model: str) -> AgentProfile:
    if not isinstance(receipt, dict) or receipt.get("format") != FORMAT_VERSION:
        raise ValueError("unsupported artifact format")
    body = {k: v for k, v in receipt.items() if k != "integrity_sha256"}
    if receipt.get("integrity_sha256") != digest(body):
        raise ValueError("compatibility artifact integrity mismatch")
    if receipt["contract"] != contract.name:
        raise ValueError("artifact applies to a different agent contract")
    if receipt["target_model"] != target_model:
        raise ValueError("artifact targets a different model")
    if receipt["source_contract_sha256"] != digest(contract_details(contract)):
        raise ValueError("protected business contract has changed")
    if receipt["source_profile_sha256"] != digest(profile_details(baseline)):
        raise ValueError("baseline agent configuration has changed")
    patch = receipt["target_profile"]
    if not isinstance(patch, dict) or set(patch) != {"instructions", "tool_descriptions"}:
        raise ValueError("invalid patch fields")
    if (not isinstance(patch["instructions"], str) or
            not 30 <= len(patch["instructions"]) <= 5000):
        raise ValueError("invalid patched instructions")
    descriptions = patch["tool_descriptions"]
    if not isinstance(descriptions, dict) or not set(descriptions).issubset(contract.tool_names()):
        raise ValueError("unsupported tool description override")
    if any(not isinstance(v, str) or not 10 <= len(v) <= 2000
           for v in descriptions.values()):
        raise ValueError("invalid tool description")
    return AgentProfile(
        instructions=patch["instructions"],
        tool_descriptions=tuple(sorted(descriptions.items())),
    )


def write_receipt(receipt: dict, path: Path) -> None:
    previous = os.umask(0o077)
    try:
        path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf8")
    finally:
        os.umask(previous)
