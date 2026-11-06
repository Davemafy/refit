"""A safe operator-only path to one REAL migration on the Vultr VM.

No public paid endpoint, no model key in browser, and no accidental Docker
fallback. The operator runs on the VM. When complete, it can atomically
publish the result into the read-only web service's run history.

The business tools are reviewed synthetic simulators, not external agents.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

from .api_service import ALLOWED_MODELS, DOMAINS, RunService


ROOT = Path("/var/lib/refit")
OPERATOR_RUNS = ROOT / "operator-runs"
PUBLIC_RUNS = ROOT / "runs"
KEY_PATH = Path("/etc/refit/inference.env")
IMAGE = "python:3.11-alpine"


def check_runtime() -> dict:
    """Hard fail if runsc is absent; never silently degrade to in-process."""
    if os.geteuid() != 0:
        raise RuntimeError("Operator migration must run as root on the trusted Vultr VM.")
    if not KEY_PATH.is_file() or not os.access(KEY_PATH, os.R_OK):
        raise RuntimeError("Vultr inference credential file not readable by operator.")
    if not shutil.which("runsc") or not shutil.which("docker"):
        raise RuntimeError("gVisor runsc and Docker must both be installed.")
    raw = subprocess.run(
        ["docker", "info", "--format", "{{json .Runtimes}}"],
        check=True, text=True, capture_output=True, timeout=12,
    ).stdout
    runtimes = json.loads(raw)
    if "runsc" not in runtimes:
        raise RuntimeError("gVisor runsc is not registered in Docker.")
    subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=12,
    )
    return {"runtime": "runsc", "image": IMAGE, "registered": True}


def publish_record(source: Path, directory: Path, uid: int, gid: int) -> Path:
    """Only publish a completed operator record; never expose active jobs.

    The published copy is created as a restrictive owned file and atomically
    renamed. A simultaneous public service restart sees a complete JSON file
    or no file, never a partial write.
    """
    payload = json.loads(source.read_text(encoding="utf8"))
    run = payload.get("run", {})
    run_id = run.get("id", "")
    if (not isinstance(run_id, str) or
            not run_id.startswith("live-") or
            source.name != run_id + ".json" or
            run.get("status") in ("queued", "running") or
            not isinstance(payload.get("events"), list) or
            len(payload["events"]) < 2):
        raise RuntimeError("Cannot publish unfinished or malformed run")
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    destination = directory / source.name
    temp = directory / ("." + run_id + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2).encode() + b"\n")
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
            os.fchown(stream.fileno(), uid, gid)
            os.fsync(stream.fileno())
        os.replace(temp, destination)
        parent = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temp.unlink(missing_ok=True)
    return destination


def run_operator(domain: str, source: str, target: str, max_requests: int,
                 publish: bool) -> int:
    check_runtime()
    os.environ["REFIT_USE_TOOL_SANDBOX"] = "1"
    os.environ["REFIT_SANDBOX_RUNTIME"] = "runsc"
    os.environ["REFIT_ENABLE_SANDBOX_DIAGNOSTICS"] = "0"
    ROOT.mkdir(parents=True, exist_ok=True)
    lock_path = ROOT / "operator.lock"
    with lock_path.open("a+b") as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another operator migration is running.") from error
        token = secrets.token_urlsafe(32)
        service = RunService(
            runs_dir=OPERATOR_RUNS, live_enabled=True, run_token=token,
            daily_limit=3, max_requests=max_requests,
        )
        accepted = service.start({
            "domain": domain, "source_model": source, "target_model": target,
        }, token)
        run_id = accepted["id"]
        print("Live migration accepted:", run_id, flush=True)
        print("gVisor requested; real model calls have a budget of",
              max_requests, flush=True)
        cursor = 0
        while True:
            news = service.get_events(run_id, after=cursor)
            cursor = news["next_after"]
            for event in news["events"]:
                print(
                    "[" + event["type"] + "] " + event["message"],
                    flush=True,
                )
            if news["terminal"]:
                break
            time.sleep(1)
        # terminal=true can become visible just before the worker finishes
        # its final fsync. Wait for the executor before publishing its snapshot.
        service.executor.shutdown(wait=True)
        result = service.get_run(run_id)
        boundary = (result.get("report") or {}).get("execution_boundary") or {}
        if (result["status"] in ("verified_adaptation", "compatible_on_sample")
                and (boundary.get("runtime") != "runsc" or
                     boundary.get("business_tools_isolated") is not True or
                     boundary.get("all_containers_removed") is not True)):
            raise RuntimeError("The migration reported success without complete gVisor evidence.")
        print(json.dumps({
            "run_id": run_id,
            "status": result["status"],
            "source": source, "target": target,
            "model_requests": result.get("model_requests"),
            "evaluation_seed": result.get("evaluation_seed"),
            "execution_isolation": result.get("execution_isolation"),
            "sandbox_worker_runs": boundary.get("worker_runs"),
            "patch_available": bool(result.get("patch")),
        }, indent=2), flush=True)
        if publish:
            account = pwd.getpwnam("refit")
            published = publish_record(
                OPERATOR_RUNS / (run_id + ".json"), PUBLIC_RUNS,
                account.pw_uid, account.pw_gid,
            )
            print("Published terminal evidence:", published, flush=True)
            subprocess.run(
                ["systemctl", "restart", "refit-public"],
                check=True, timeout=20,
            )
            url = "http://127.0.0.1:8097/api/runs/" + run_id
            for _ in range(30):
                try:
                    with urlopen(url, timeout=2) as response:
                        observed = json.load(response)
                    if observed["status"] == result["status"]:
                        print("Read-only API now serves:", run_id, flush=True)
                        break
                except (OSError, ValueError, KeyError):
                    time.sleep(.5)
            else:
                raise RuntimeError("Published file exists but public service did not expose it.")
        return 0 if result["status"] in (
            "verified_adaptation", "compatible_on_sample"
        ) else 1


def main():
    parser = argparse.ArgumentParser(description="Bounded Vultr/gVisor live migration")
    parser.add_argument("--domain", choices=list(DOMAINS), required=True)
    parser.add_argument("--source", choices=ALLOWED_MODELS, required=True)
    parser.add_argument("--target", choices=ALLOWED_MODELS, required=True)
    parser.add_argument("--max-requests", type=int, default=160)
    parser.add_argument("--execute", action="store_true",
                        help="Actually use inference credits (never the default).")
    parser.add_argument("--publish", action="store_true",
                        help="After terminal result, publish in read-only public UI.")
    args = parser.parse_args()
    if args.source == args.target or not 1 <= args.max_requests <= 200:
        parser.error("source/target must differ and request budget must be 1–200")
    if args.publish and not args.execute:
        parser.error("--publish requires explicit --execute")
    if not args.execute:
        print(json.dumps({
            "mode": "dry_run_only", "domain": args.domain,
            "source": args.source, "target": args.target,
            "max_requests": args.max_requests,
            "requirements": "Vultr VM root, registered gVisor runsc, private inference key",
            "no_model_requests": True,
        }, indent=2))
        return
    try:
        raise_code = run_operator(
            args.domain, args.source, args.target,
            args.max_requests, args.publish,
        )
    except Exception as exc:
        # Avoid echoing HTTP provider responses or credential-bearing tracebacks.
        print("Operator migration stopped:", type(exc).__name__, file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(raise_code)


if __name__ == "__main__":
    main()
