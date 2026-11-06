"""Disposable, network-isolated execution of Python *generated tests*.

The orchestrator invokes this on a trusted Vultr host; never give sandboxed
code the Docker socket, inference key, host home, or user-supplied mount paths.
Docker's shared kernel is not equivalent to a microVM. A configured gVisor
runsc runtime is preferable when available and must be verified on the VM.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from typing import Any

IMAGE = "python:3.11-alpine"
MAX_CODE_BYTES = 20_000
MAX_INPUT_BYTES = 65_536
OUTPUT_LIMIT = 64 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf8")


def chain_events(events: list[dict]) -> list[dict]:
    """A host-generated tamper-evident record, not kernel syscall auditing."""
    out = []
    previous = "0" * 64
    for item in events:
        entry = {"sequence": len(out) + 1, "previous_hash": previous,
                 "event": item}
        previous = _sha(_canonical(entry))
        out.append({**entry, "hash": previous})
    return out


def verify_chain(ledger: list[dict]) -> bool:
    previous = "0" * 64
    for i, entry in enumerate(ledger):
        if (entry.get("sequence") != i + 1 or
                entry.get("previous_hash") != previous):
            return False
        body = {k: entry[k] for k in ("sequence", "previous_hash", "event")}
        if entry.get("hash") != _sha(_canonical(body)):
            return False
        previous = entry["hash"]
    return True


class SandboxUnavailable(RuntimeError):
    pass


class DockerSandbox:
    """Runs one script per disposable container, never a persistent shell.

    Only use this class behind an authenticated, budget-limited orchestrator;
    don't expose arbitrary Python uploads to the public API.
    """

    def __init__(self, runtime: str = "runc", image: str = IMAGE,
                 timeout_seconds: int = 12, docker: str = "docker"):
        if runtime not in ("runc", "runsc"):
            raise ValueError("runtime must be Docker runc or registered gVisor runsc")
        if image != IMAGE:
            raise ValueError("image is pinned to the approved image name")
        if not 2 <= timeout_seconds <= 30:
            raise ValueError("timeout outside approved range")
        self.runtime = runtime
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.docker = docker

    def _command(self, name: str, directory: Path, cidfile: Path) -> list[str]:
        return [
            self.docker, "run", "--rm", "--name", name,
            "--cidfile", str(cidfile),
            "--runtime", self.runtime,
            "--network", "none",
            "--user", "65534:65534",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "32",
            "--memory", "128m",
            "--memory-swap", "128m",
            "--cpus", "0.5",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
            "--log-driver", "none",
            "--mount", f"type=bind,src={directory},dst=/refit-input,readonly",
            "--workdir", "/tmp",
            self.image, "python", "-I", "-S", "-B", "/refit-input/program.py",
        ]

    def run(self, code: str, inputs: dict | None = None,
            label: str = "generated_test") -> dict:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Python source must be nonempty")
        body = code.encode("utf8")
        if len(body) > MAX_CODE_BYTES or "\x00" in code:
            raise ValueError("Python source is too large or contains NUL")
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            raise ValueError("inputs must be a JSON object")
        data = _canonical(inputs)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("input JSON exceeds budget")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", label):
            raise ValueError("invalid run label")
        if not shutil.which(self.docker):
            raise SandboxUnavailable("Docker CLI not installed")
        if not shutil.which("prlimit"):
            raise SandboxUnavailable("prlimit is required to cap host-side output")
        name = "refit-" + secrets.token_hex(10)
        started = time.monotonic()
        policy = {
            "runtime": self.runtime, "image": self.image,
            "network": "none", "readonly_root": True,
            "no_new_privileges": True, "capabilities": "dropped_all",
            "user": "65534:65534", "memory_mb": 128,
            "pids_limit": 32, "cpus": 0.5,
            "timeout_seconds": self.timeout_seconds,
            "output_limit_bytes_per_stream": OUTPUT_LIMIT,
        }
        events = [{"type": "launch_requested", "label": label,
                   "code_sha256": _sha(body), "input_sha256": _sha(data),
                   "policy": policy}]
        with tempfile.TemporaryDirectory(prefix="refit-sandbox-") as tmp:
            directory = Path(tmp) / "payload"
            directory.mkdir(mode=0o755)
            source = directory / "program.py"
            source.write_bytes(body)
            source.chmod(0o644)
            data_file = directory / "input.json"
            data_file.write_bytes(data)
            data_file.chmod(0o644)
            cidfile = Path(tmp) / "container.id"
            exit_code = None
            timed_out = False
            startup_error = None
            # prlimit limits the *host Docker CLI's* writes to each output
            # file. The container's own write capacity is separately bounded.
            command = [
                "prlimit",
                f"--fsize={OUTPUT_LIMIT}:{OUTPUT_LIMIT}",
                "--",
                *self._command(name, directory, cidfile),
            ]
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                try:
                    proc = subprocess.run(
                        command, stdout=stdout, stderr=stderr,
                        timeout=self.timeout_seconds, check=False,
                    )
                    exit_code = proc.returncode
                except subprocess.TimeoutExpired:
                    timed_out = True
                except (OSError, subprocess.SubprocessError) as exc:
                    startup_error = type(exc).__name__
                # A timed-out Docker CLI may leave an active container. Kill
                # it by a random fixed name. Never rely on --rm alone.
                cleanup = subprocess.run(
                    [self.docker, "rm", "-f", name],
                    capture_output=True, timeout=8, check=False,
                )
                inspect = subprocess.run(
                    [self.docker, "container", "inspect", name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=8, check=False,
                )
                # This check proves absence at inspection time. It does not
                # prove anything about containers with *different* names.
                removed = inspect.returncode != 0
                stdout.seek(0)
                stderr.seek(0)
                out = stdout.read(OUTPUT_LIMIT)
                err = stderr.read(OUTPUT_LIMIT)
            container_created = (
                (cidfile.is_file() and bool(cidfile.read_text().strip()))
                or (exit_code is not None and exit_code not in (125, 126, 127))
            )
            duration_ms = round((time.monotonic() - started) * 1000)
        events.append({
            "type": "execution_observed", "container_created": container_created,
            "exit_code": exit_code, "timed_out": timed_out,
            "startup_error": startup_error,
            "stdout_sha256": _sha(out), "stderr_sha256": _sha(err),
            "duration_ms": duration_ms,
        })
        events.append({
            "type": "cleanup_checked", "container_absent": removed,
            "cleanup_exit_code": cleanup.returncode,
        })
        ledger = chain_events(events)
        status = (
            "timeout" if timed_out else
            "runtime_error" if startup_error or not container_created else
            "passed" if exit_code == 0 else "execution_failed"
        )
        # Never infer "blocked" solely from a code's printed claim.
        return {
            "status": status, "label": label, "runtime": self.runtime,
            "image": self.image, "exit_code": exit_code,
            "timed_out": timed_out, "duration_ms": duration_ms,
            "stdout": out.decode("utf8", errors="replace"),
            "stderr": err.decode("utf8", errors="replace"),
            "code_sha256": _sha(body), "input_sha256": _sha(data),
            "container_created": container_created,
            "container_removed_verified": removed,
            "ledger": ledger, "ledger_valid": verify_chain(ledger),
            "warning": (
                "Container isolation is not a separate-kernel security boundary."
                if self.runtime == "runc" else
                "gVisor isolation requires runtime verification on the target Vultr host."
            ),
        }


SAFE_PROBE = """\
import json
from pathlib import Path

values = json.loads(Path('/refit-input/input.json').read_text())
counts = values['counts']
assert counts['source_passed'] == 8
assert counts['target_passed'] < counts['source_passed']
print(json.dumps({'regression_detected': True, 'delta': counts['source_passed'] - counts['target_passed']}))
"""

HOSTILE_PROBE = """\
import json
import os
import socket
from pathlib import Path

results = {}
try:
    Path('/etc/refit/inference.env').read_text()
    results['key_file'] = 'unexpectedly_readable'
except OSError as exc:
    results['key_file'] = type(exc).__name__
results['key_in_env'] = any('VULTR_INFERENCE_API_KEY' in name for name in os.environ)
try:
    socket.getaddrinfo('example.com', 443)
    results['dns'] = 'unexpectedly_resolved'
except OSError as exc:
    results['dns'] = type(exc).__name__
try:
    socket.create_connection(('1.1.1.1', 80), timeout=1)
    results['outbound_connection'] = 'unexpectedly_connected'
except OSError as exc:
    results['outbound_connection'] = type(exc).__name__
try:
    Path('/escape-refit-probe').write_text('should fail')
    results['root_write'] = 'unexpectedly_writable'
except OSError as exc:
    results['root_write'] = type(exc).__name__
print(json.dumps(results, sort_keys=True))
"""


def main() -> None:
    """Local dry-run entry point; do not expose a public arbitrary-code API."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", choices=("safe", "hostile"), default="safe")
    parser.add_argument("--runtime", choices=("runc", "runsc"), default="runc")
    options = parser.parse_args()
    code = SAFE_PROBE if options.fixture == "safe" else HOSTILE_PROBE
    data = {"counts": {"source_passed": 8, "target_passed": 6}}
    result = DockerSandbox(runtime=options.runtime).run(
        code, data, label=options.fixture + "_probe")
    print(json.dumps(result, indent=2))
    if not result["ledger_valid"] or not result["container_removed_verified"]:
        raise SystemExit(2)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
