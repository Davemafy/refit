"""Bounded Docker removal with explicit, fail-closed absence evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import subprocess


def _observe(command: list[str], env: dict[str, str] | None, timeout: int) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                env=env, timeout=timeout, check=False)
        return {"returncode": result.returncode, "stdout": result.stdout or "",
                "stderr": result.stderr or "", "error": None}
    except (OSError, subprocess.SubprocessError) as exc:
        # A transport error or timeout is unknown state, never proof of absence.
        return {"returncode": None, "stdout": "", "stderr": "",
                "error": type(exc).__name__}


def _missing(result: dict, name: str) -> bool:
    expected = {
        f"Error: No such container: {name}",
        f"Error: No such object: {name}",
        f"Error response from daemon: No such container: {name}",
        f"Error response from daemon: No such object: {name}",
    }
    return (result["error"] is None and result["returncode"] == 1
            and result["stderr"].strip() in expected
            and result["stdout"].strip() in ("", "[]"))


def remove_and_verify(docker: str, name: str, *, env: dict[str, str] | None = None,
                      timeout: int = 8) -> dict:
    """Remove one owned container and confirm its absence on a reachable daemon.

    The caller must use the same Docker executable and environment for launch
    and cleanup. No retries, context changes, or fallback runtimes are attempted.
    An auto-removed container is acceptable; unknown errors remain unverified.
    """
    if not re.fullmatch(r"refit-[a-z0-9][a-z0-9_.-]{0,119}", name):
        raise ValueError("cleanup requires an owned Refit container name")
    if not 1 <= timeout <= 8:
        raise ValueError("cleanup timeout must be 1..8 seconds per command")
    removal = _observe([docker, "rm", "-f", name], env, timeout)
    inspection = _observe([docker, "container", "inspect", name], env, timeout)
    health = _observe([docker, "info", "--format", "{{json .ID}}"], env, timeout)
    daemon_id = None
    if health["error"] is None and health["returncode"] == 0 and not health["stderr"].strip():
        try:
            value = json.loads(health["stdout"])
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9:_-]{1,200}", value):
                daemon_id = value
        except (ValueError, TypeError):
            pass
    removal_ok = (removal["error"] is None and
                  (removal["returncode"] == 0 or _missing(removal, name)))
    absent = _missing(inspection, name)
    verified = removal_ok and absent and daemon_id is not None
    reason = ("verified_absent" if verified else "removal_failed" if not removal_ok else
              "absence_not_established" if not absent else "daemon_health_not_established")
    # Bound report output while matching against the complete observed response.
    for result in (removal, inspection, health):
        result["stdout"] = result["stdout"][:1000]
        result["stderr"] = result["stderr"][:1000]
    return {"version": 1, "container_name": name, "verified": verified,
            "reason": reason, "observed_at": datetime.now(timezone.utc).isoformat(),
            "removal": removal, "inspection": inspection,
            "daemon_health": health, "daemon_id": daemon_id}
