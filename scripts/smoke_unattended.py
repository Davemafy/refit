"""Independent zero-inference production acceptance for unattended Refit use.

A healthy landing page is not enough: the public service must have enough
remaining authorized requests for ONE complete agent migration, and must not
be quarantined. The check never creates users, sends model prompts, pulls
source, or touches privileged Docker services.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen

from .smoke_platform_https import check as https_check


def inspect(origin: str) -> dict:
    public = https_check(origin)
    revision = public["deployed_revision"]
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise AssertionError("The public service did not expose a valid deployed SHA")
    try:
        response = urlopen(origin.rstrip("/") + "/api/application/readiness", timeout=12)
    except HTTPError as error:
        response = error
    with response:
        status = response.status
        raw = response.read(4097)
    if len(raw) > 4096:
        raise AssertionError("Oversized readiness result")
    readiness = json.loads(raw)
    if not isinstance(readiness, dict) or readiness.get("revision") != revision:
        raise AssertionError("Readiness and deployed revision disagree")
    if readiness.get("online") is not True:
        raise AssertionError("Live service reports unavailable")
    if status != 200 or readiness.get("can_start_complete_migration") is not True:
        return {"ok": False, "reason": readiness.get("reason") or "not_ready",
                "revision": revision,
                "capacity_resets_at": readiness.get("capacity_resets_at")}
    if readiness.get("minimum_inference_requests") != 7:
        raise AssertionError("Unexpected complete migration request requirement")
    if readiness.get("capacity_state") != "ready":
        raise AssertionError("Inconsistent production capacity")
    return {"ok": True, "reason": None, "revision": revision,
            "capacity_resets_at": readiness.get("capacity_resets_at")}


def probe(origin: str, attempts=3, delay=10, check=inspect, sleeper=time.sleep):
    if attempts not in range(1, 6) or not 0 <= delay <= 60:
        raise ValueError("The unattended probe requires bounded attempts and delay")
    history = []
    for attempt in range(attempts):
        try:
            item = check(origin)
            if item["ok"]:
                return {"status": "ready", "attempts": attempt + 1,
                        "reason": None, "revision": item["revision"],
                        "checked_at": datetime.now(timezone.utc).isoformat()}
            history.append(item["reason"])
        except (OSError, TimeoutError, HTTPError, ValueError, AssertionError, KeyError) as exc:
            # Avoid leaking upstream HTML into the public incident title/body.
            history.append(type(exc).__name__)
        if attempt < attempts - 1:
            sleeper(delay)
    return {"status": "degraded", "attempts": attempts,
            "reason": history[-1], "observations": history,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://80.240.30.92")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--output", type=Path,
                        default=Path("/tmp/refit-unattended-readiness.json"))
    args = parser.parse_args()
    result = probe(args.origin, args.attempts, args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
