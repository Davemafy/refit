"""Contain each existing Refit tool-using agent scenario in Docker.

The host owns the model client and protected orchestration. Each tool call
crosses a JSONL pipe to one disposable, networkless scenario worker. No
Vultr credentials or user-supplied agent code enter the worker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import selectors
import shutil
import subprocess
import tempfile
import time
from typing import Any

from .migration_engine import ReplayCase, migrate
from .docker_cleanup import remove_and_verify
from . import refund_adapter, deployment_incident_probe


ROOT = Path(__file__).resolve().parent.parent
DOMAINS = {"refund": refund_adapter, "deployment": deployment_incident_probe}
# Only audited Python modules are mounted. Never mount a workspace or .env.
SOURCE_FILES = (
    "sandbox_tool_worker.py", "refund_adapter.py",
    "deployment_incident_probe.py", "migration_engine.py",
    "refit_vultr_probe.py", "refit_stress_probe.py",
)
MAX_REQUEST = 32768
MAX_RESPONSE = 131072
REPLY_SECONDS = 8


class ToolSandboxUnavailable(RuntimeError):
    pass


class ToolSandboxEnvironment:
    def __init__(self, domain: str, phase: str, seed: int,
                 case_index: int, records: list[dict],
                 runtime: str = "runc", image: str = "python:3.11-alpine",
                 docker: str = "docker"):
        if domain not in DOMAINS or phase not in ("train", "validation", "holdout"):
            raise ValueError("invalid scenario")
        if runtime not in ("runc", "runsc"):
            raise ValueError("invalid sandbox runtime")
        if image != "python:3.11-alpine":
            raise ValueError("unapproved sandbox image")
        if not 0 <= seed < 2147483647 or not 0 <= case_index < 16:
            raise ValueError("invalid seed or scenario index")
        if not shutil.which(docker):
            raise ToolSandboxUnavailable("Docker is not installed")
        self.domain = domain
        self.phase = phase
        self.seed = seed
        self.index = case_index
        self.runtime = runtime
        self.records = records
        self.events = []
        self.started = time.monotonic()
        self.closed = False
        self.cleanup_verified = False
        self.docker_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        self.container = "refit-tool-" + secrets.token_hex(10)
        self.docker = docker
        self.temp = tempfile.TemporaryDirectory(prefix="refit-tool-src-")
        self.proc = None
        self.source_dir = Path(self.temp.name) / "source"
        self.source_dir.mkdir(mode=0o755)
        self.source_dir.chmod(0o755)
        package_dir = self.source_dir / "scripts"
        package_dir.mkdir(mode=0o755)
        package_dir.chmod(0o755)
        try:
            for file in SOURCE_FILES:
                original = ROOT / "scripts" / file
                destination = package_dir / file
                shutil.copyfile(original, destination)
                destination.chmod(0o644)
            command = [
                docker, "run", "--rm", "-i", "--name", self.container,
                "--runtime", runtime, "--network", "none",
                "--user", "65534:65534", "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--pids-limit", "32", "--memory", "128m",
                "--memory-swap", "128m", "--cpus", "0.5",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
                "--log-driver", "none",
                "--mount", (
                    "type=bind,src=" + str(self.source_dir)
                    + ",dst=/refit-source,readonly"
                ),
                "--workdir", "/tmp",
                image, "python", "-I", "-S", "-B", "-u",
                "/refit-source/scripts/sandbox_tool_worker.py",
                "--domain", domain, "--phase", phase, "--seed", str(seed),
                "--case-index", str(case_index),
            ]
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
                env=self.docker_env,
            )
        except Exception:
            self.temp.cleanup()
            raise

    def _exchange(self, command: dict) -> dict:
        if self.closed or self.proc is None:
            raise ToolSandboxUnavailable("sandbox is closed")
        if time.monotonic() - self.started > 900:
            raise ToolSandboxUnavailable("sandbox session exceeded deadline")
        request = json.dumps(command, separators=(",", ":")).encode() + b"\n"
        if len(request) > MAX_REQUEST:
            raise ValueError("sandbox request exceeds budget")
        if self.proc.poll() is not None:
            raise ToolSandboxUnavailable("sandbox process exited unexpectedly")
        try:
            assert self.proc.stdin is not None
            assert self.proc.stdout is not None
            # Own the unbuffered pipes and bound the complete exchange. A
            # readable prefix is not a complete JSONL reply; readline() could
            # otherwise block forever after the selector's first notification.
            os.set_blocking(self.proc.stdin.fileno(), False)
            os.set_blocking(self.proc.stdout.fileno(), False)
            deadline = min(time.monotonic() + REPLY_SECONDS, self.started + 900)
            with selectors.DefaultSelector() as selector:
                selector.register(self.proc.stdin, selectors.EVENT_WRITE)
                sent = 0
                while sent < len(request):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ToolSandboxUnavailable("sandbox tool response timed out")
                    try:
                        written = os.write(self.proc.stdin.fileno(), request[sent:])
                    except BlockingIOError:
                        continue
                    if written <= 0:
                        raise ToolSandboxUnavailable("sandbox request pipe closed")
                    sent += written
                selector.unregister(self.proc.stdin)
                selector.register(self.proc.stdout, selectors.EVENT_READ)
                response = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ToolSandboxUnavailable("sandbox tool response timed out")
                    try:
                        chunk = os.read(self.proc.stdout.fileno(),
                                        min(4096, MAX_RESPONSE + 1 - len(response)))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise ToolSandboxUnavailable("sandbox response missing or incomplete")
                    response.extend(chunk)
                    if len(response) > MAX_RESPONSE:
                        raise ToolSandboxUnavailable("sandbox response oversized")
                    if b"\n" in response:
                        if response.index(b"\n") != len(response) - 1:
                            raise ToolSandboxUnavailable("unexpected sandbox response framing")
                        break
            result = json.loads(response)
            if not isinstance(result, dict) or "error" in result:
                raise ToolSandboxUnavailable("sandbox rejected the tool operation")
            return result
        except (OSError, ValueError, BrokenPipeError) as exc:
            raise ToolSandboxUnavailable("sandbox tool transport failed") from exc

    def call(self, name: str, arguments: Any) -> dict:
        response = self._exchange({
            "op": "call", "tool": name, "arguments": arguments
        })
        answer = response.get("result")
        if not isinstance(answer, dict):
            raise ToolSandboxUnavailable("invalid tool result from sandbox")
        self.events.append({
            "tool": name, "arguments": arguments, "result": answer,
        })
        return answer

    def verify(self) -> dict:
        """Independently replay trusted synthetic-tool traces outside sandbox.

        A sandbox-side verdict cannot decide acceptance on its own. For the
        two fixed built-in environments only, replay the declared tool calls
        against a new host-owned deterministic state and compare every
        state transition, tool result, and final business verdict. NEVER do
        this with imported or untrusted tool implementations on the host.
        """
        try:
            result = self._exchange({"op": "verify"})
            verdict = result.get("verdict")
            trace = result.get("events")
            if not isinstance(verdict, dict) or not isinstance(trace, list):
                raise ToolSandboxUnavailable("invalid sandbox verifier response")
            if len(trace) > 40 or not all(isinstance(e, dict) for e in trace):
                raise ToolSandboxUnavailable("invalid sandbox execution trace")
            original_case = DOMAINS[self.domain].make_cases(
                self.seed, self.phase
            )[self.index]
            oracle = original_case.environment()
            try:
                for entry in trace:
                    name = entry.get("tool")
                    if not isinstance(name, str) or len(name) > 100:
                        raise ToolSandboxUnavailable("invalid tool in sandbox trace")
                    result_on_host = oracle.call(name, entry.get("arguments"))
                    if result_on_host != entry.get("result"):
                        raise ToolSandboxUnavailable("sandbox tool result mismatch")
                expected = oracle.verify()
                if oracle.events != trace or expected != verdict:
                    raise ToolSandboxUnavailable("protected business oracle mismatch")
            finally:
                close = getattr(oracle, "close", None)
                if callable(close):
                    close()
            self.events = trace
            return expected
        except (ToolSandboxUnavailable, ValueError, KeyError, IndexError):
            return {"passed": False, "unsafe_attempts": 0,
                    "sandbox_error": "protected_oracle_rejected_trace"}

    def close(self) -> None:
        if self.closed:
            if not self.cleanup_verified:
                raise ToolSandboxUnavailable("container cleanup previously unverified")
            return
        self.closed = True
        process_error = None
        try:
            try:
                if self.proc is not None:
                    try:
                        if self.proc.poll() is None:
                            try:
                                assert self.proc.stdin
                                self.proc.stdin.write(b'{"op":"close"}\n')
                                self.proc.stdin.flush()
                            except (OSError, BrokenPipeError):
                                pass
                            self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=2)
                    finally:
                        if self.proc.stdin:
                            self.proc.stdin.close()
                        if self.proc.stdout:
                            self.proc.stdout.close()
            except (OSError, subprocess.SubprocessError) as exc:
                process_error = type(exc).__name__
            # Even a failed CLI shutdown must still attempt container removal.
            cleanup = remove_and_verify(self.docker, self.container, env=self.docker_env)
            self.cleanup_verified = cleanup["verified"] and process_error is None
            self.records.append({
                "domain": self.domain, "phase": self.phase,
                "case_index": self.index, "runtime": self.runtime,
                "network": "none", "read_only_root": True,
                "container_absent": self.cleanup_verified,
                "cleanup_evidence": cleanup,
                "process_cleanup_error": process_error,
                "duration_ms": round((time.monotonic() - self.started) * 1000),
            })
            if not self.cleanup_verified:
                raise ToolSandboxUnavailable("container cleanup not verified: " + cleanup["reason"])
        finally:
            self.temp.cleanup()


def sandbox_cases(domain: str, seed: int, phase: str, records: list[dict],
                  runtime: str = "runc") -> list[ReplayCase]:
    if domain not in DOMAINS:
        raise ValueError("unknown domain")
    known_cases = DOMAINS[domain].make_cases(seed, phase)
    output = []
    for index, original in enumerate(known_cases):
        def factory(case_index=index):
            return ToolSandboxEnvironment(
                domain, phase, seed, case_index, records, runtime=runtime
            )
        output.append(ReplayCase(original.name, original.request, factory))
    return output


def migrate_in_tool_sandboxes(client, domain: str, source: str,
                             target: str, repair_model: str, seed: int,
                             runtime: str = "runc", progress=None) -> dict:
    """Full source/target/validation/holdout agent replay with isolated tools."""
    if domain not in DOMAINS:
        raise ValueError("unknown domain")
    if runtime not in ("runc", "runsc"):
        raise ValueError("unsupported runtime")
    module = DOMAINS[domain]
    records: list[dict] = []
    result = migrate(
        client, module.CONTRACT, source, target, repair_model,
        module.BASE_PROFILE,
        sandbox_cases(domain, seed, "train", records, runtime),
        lambda: sandbox_cases(domain, seed + 109, "validation", records, runtime),
        lambda: sandbox_cases(domain, seed + 919, "holdout", records, runtime),
        progress=progress,
    )
    result["execution_boundary"] = {
        "type": "docker_tool_sandbox",
        "runtime": runtime,
        "business_tools_isolated": True,
        "worker_runs": len(records),
        "all_containers_removed": bool(records) and all(
            x["container_absent"] for x in records
        ),
        "cases": records,
        "note": (
            "Model calls remain on host. Synthetic business tools and "
            "their simulator verifier execute inside disposable containers. "
            "Host controls accepted patch and business invariants."
        ),
    }
    return result
