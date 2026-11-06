"""Capture a checkout identity once, when the service starts."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess


def capture_revision(root: Path) -> dict:
    identity = {"commit": None, "tracked_files_clean": None,
                "captured_at": datetime.now(timezone.utc).isoformat()}
    # The public process intentionally runs as a different, read-only user.
    # Trust this exact root-owned application checkout, never all Git paths.
    command = ["git", "-c", f"safe.directory={root.resolve()}"]
    try:
        head = subprocess.run([*command, "rev-parse", "HEAD"], cwd=root,
                              text=True, capture_output=True, timeout=3, check=False)
        if head.returncode or not re.fullmatch(r"[a-f0-9]{40}", head.stdout.strip()):
            return identity
        identity["commit"] = head.stdout.strip()
        state = subprocess.run([*command, "status", "--porcelain", "--untracked-files=no"],
                               cwd=root, text=True, capture_output=True, timeout=3, check=False)
        if state.returncode == 0:
            identity["tracked_files_clean"] = not state.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return identity
