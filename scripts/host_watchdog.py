"""Conservative on-host liveness repair for Refit (zero inference).

Run by a root-owned systemd timer, not by the public application. Restarts an
unresponsive service only after three consecutive independent checks, only
when deployment is not in progress, and only when no agent/diagnostic worker
is active. This never clears safety quarantine, changes spending limits or
replays a potentially billed model call.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen

LOCK = Path("/run/lock/refit-host-deployment.lock")
COUNTER = Path("/run/refit-watchdog/misses")
PROMOTED = Path("/usr/local/share/refit/deployed_revision")
API = "http://127.0.0.1:8098/api/application/release"
WORKER = re.compile(r"(?:refit-app|refit)-[a-f0-9]{20}\Z")


def valid_release(expected: str) -> bool:
    try:
        with urlopen(API, timeout=4) as response:
            if response.status != 200:
                return False
            raw = response.read(513)
        return json.loads(raw).get("revision") == expected
    except (OSError, TimeoutError, ValueError, KeyError, TypeError):
        return False


def active_workers() -> bool:
    """Fail closed if Docker cannot establish whether jobs are in flight."""
    result = subprocess.run(
        ["/usr/bin/docker", "ps", "--format", "{{.Names}}"],
        text=True, capture_output=True, timeout=7, check=False,
    )
    if result.returncode:
        raise RuntimeError("Cannot establish current workers: Docker unavailable")
    return any(WORKER.fullmatch(row.strip()) for row in result.stdout.splitlines())


def missed_count():
    try:
        value = COUNTER.read_text().strip()
        return int(value) if re.fullmatch(r"[0-9]{1,3}", value) else 0
    except FileNotFoundError:
        return 0


def record_missed(count):
    COUNTER.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp = COUNTER.with_suffix(".next")
    tmp.write_text(str(count) + "\n")
    tmp.replace(COUNTER)


def repair():
    if os.geteuid() != 0:
        raise PermissionError("The host watchdog must be root-owned")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "deployment_in_progress", "changed": False}

        expected = PROMOTED.read_text().strip()
        if not re.fullmatch(r"[a-f0-9]{40}", expected):
            raise ValueError("Missing immutable promoted Refit revision")

        if valid_release(expected):
            record_missed(0)
            return {"status": "healthy", "changed": False}

        misses = min(999, missed_count() + 1)
        record_missed(misses)
        if misses < 3:
            return {"status": "unhealthy_observing", "checks_failed": misses, "changed": False}

        try:
            if active_workers():
                return {"status": "active_worker_preserved", "checks_failed": misses,
                        "changed": False}
        except (OSError, subprocess.TimeoutExpired, RuntimeError):
            return {"status": "worker_state_unknown", "checks_failed": misses,
                    "changed": False}

        # The release endpoint is a cheap local HTTP GET, not an inference
        # operation. Restore the service only when no workers can be affected.
        result = subprocess.run(
            ["/usr/bin/systemctl", "restart", "refit-application.service"],
            capture_output=True, timeout=25, check=False,
        )
        if result.returncode:
            return {"status": "restart_failed", "changed": False}
        if valid_release(expected):
            record_missed(0)
            return {"status": "recovered", "changed": True}
        return {"status": "restart_unhealthy", "changed": True}


if __name__ == "__main__":
    try:
        outcome = repair()
        print(json.dumps(outcome, sort_keys=True), flush=True)
        sys.exit(1 if outcome["status"] in {"restart_failed", "restart_unhealthy"} else 0)
    except (OSError, PermissionError, ValueError) as exc:
        print(json.dumps({"status": "watchdog_inoperative",
                          "reason": type(exc).__name__}), flush=True)
        sys.exit(1)
