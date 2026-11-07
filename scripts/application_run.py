"""Application-native execution through the existing gVisor and Vultr boundaries."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

from .container_agent import command, frame, send, validate_completion
from .docker_cleanup import remove_and_verify
from .migration_engine import AgentContract, AgentProfile, ReplayCase, fingerprint, migrate
from .refit_vultr_probe import ENDPOINT

MODELS = ("deepseek-v4.1-flash-1017", "glm-5.2")
BUDGET_LIMIT = 24
CASE_SECONDS = 45
RUN_SECONDS = 360
CASE_CALLS = 4
NODE_PACKAGES = json.loads((Path(__file__).resolve().parents[1] /
    "integrations/application/node/package.json").read_text())["dependencies"]


class RunStopped(RuntimeError):
    pass


def llm_setup():
    version = "0.37.1"
    cases = []
    for split, request in (
        ("train", "Use llm_version. Reply with only the version it returns."),
        ("validation", "Check the installed LLM release with llm_version. Output only the exact version number."),
        ("holdout", "Call llm_version to obtain the installed release. Return just its value without decoration."),
    ):
        cases.append({"name": split, "split": split, "prompt": request, "stdout": version,
                      "tool": "llm_version", "tool_result": version})
    return {"module": "llm", "args": ["prompt", "--no-stream", "--no-log", "--chain-limit",
            "2", "-m", "{model}", "--tool", "llm_version", "--", "{prompt}"], "cases": cases}


def configuration(snapshot, supplied=None):
    preset = snapshot["discovery"]["preset"]
    if preset and supplied is None:
        return {**llm_setup(), "seam": "llm"}
    runtime = snapshot["discovery"]["runtime"]
    key = "entry" if runtime == "typescript" else "module"
    if not isinstance(supplied, dict) or set(supplied) != {key, "args", "cases"}:
        raise ValueError(snapshot["discovery"]["setup"] or "Provide an entry, arguments and evaluation cases.")
    entry, args, cases = (supplied[name] for name in (key, "args", "cases"))
    if runtime == "typescript":
        if (not isinstance(entry, str) or entry not in snapshot["files"]
                or not entry.endswith((".ts", ".mts", ".js", ".mjs"))
                or entry.endswith(".d.ts")):
            raise ValueError("Choose a TypeScript or JavaScript CLI file present in the imported source.")
        if "package.json" not in snapshot["files"]:
            raise ValueError("TypeScript execution is unavailable without a package.json declaring its runtime dependencies.")
        try:
            package = json.loads(base64.b64decode(snapshot["files"]["package.json"]))
            deps = package.get("dependencies", {})
            if not isinstance(deps, dict) or not all(isinstance(v, str) for v in deps.values()):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("Provide a valid package.json with runtime dependencies.") from None
        for dependency, spec in sorted(deps.items()):
            pinned = NODE_PACKAGES.get(dependency)
            parsed = re.fullmatch(r"(\^)?(\d+)\.(\d+)\.(\d+)", spec)
            if pinned and parsed:
                minimum = tuple(map(int, parsed.groups()[1:]))
                available = tuple(map(int, pinned.split(".")))
                if minimum == available or (parsed[1] and minimum[0] == available[0] and minimum <= available):
                    continue
            raise ValueError(f"Dependency {dependency} ({spec}) is outside the reviewed Node runtime. "
                             "Upload a CLI-only source snapshot with its required dependencies.")
    elif (not isinstance(entry, str) or len(entry) > 120
            or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", entry)
            or not any(entry.replace(".", "/") + suffix in snapshot["files"]
                       for suffix in (".py", "/__main__.py"))):
        raise ValueError("Choose a Python module present in the uploaded source.")
    if (not isinstance(args, list) or len(args) > 24 or
            any(not isinstance(arg, str) or len(arg) > 1024 or "\x00" in arg for arg in args)
            or not any("{prompt}" in arg for arg in args)):
        raise ValueError("Supply up to 24 command arguments, including a {prompt} placeholder.")
    if not isinstance(cases, list) or not 3 <= len(cases) <= 6:
        raise ValueError("Provide 3 to 6 cases covering train, validation and holdout.")
    names = set()
    prompts = set()
    for case in cases:
        if (not isinstance(case, dict) or set(case) not in ({"name", "split", "prompt", "stdout"}, {"name", "split", "prompt", "stdout", "tool", "tool_result"})
                or any(not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\x00" in value
                       for value in case.values())
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", case["name"])
                or case["split"] not in {"train", "validation", "holdout"}
                or case["name"] in names or case["prompt"] in prompts):
            raise ValueError("Give each case a unique name and prompt, a valid split, and exact expected stdout.")
        names.add(case["name"])
        prompts.add(case["prompt"])
    if {case["split"] for case in cases} != {"train", "validation", "holdout"}:
        raise ValueError("Each split needs at least one independent case.")
    return {**supplied, "seam": "openai-env"}


def native_export(snapshot, setup, model, instructions=""):
    config = {"format": "refit.application-export.v1", "model": model,
              "source_sha256": snapshot["source_sha256"], "repository": snapshot["repository"],
              "revision": snapshot["revision"], "args": setup["args"],
              **{key: setup[key] for key in ("entry", "module") if key in setup},
              "instructions": instructions, "seam": setup["seam"]}
    if setup["seam"] == "llm":
        config["extra-openai-models.yaml"] = [{"model_id": model, "model_name": model,
            "api_base": ENDPOINT.removesuffix("/chat/completions"), "api_key_name": "vultr",
            "can_stream": False, "supports_tools": True}]
    else:
        config["environment"] = {"OPENAI_MODEL": model,
            "OPENAI_BASE_URL": ENDPOINT.removesuffix("/chat/completions")}
    config["integrity_sha256"] = fingerprint(config)
    return config


def run_migration(snapshot, setup, source, target, image, broker, event, stopped):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    started = time.monotonic()
    image_id = subprocess.check_output(["docker", "image", "inspect", "--format={{.Id}}", image],
                                      text=True, timeout=10, env=env).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Application runtime image identity is unavailable.")
    event("runtime_ready", {"image_id": image_id, "seconds": round(time.monotonic() - started, 3)})
    deadline = started + RUN_SECONDS

    def check():
        if stopped():
            raise RunStopped("cancelled")
        if time.monotonic() >= deadline:
            raise RunStopped("run_timeout")

    def execute(model, profile, case, phase, native=None):
        check()
        case_start = time.monotonic()
        limit = min(deadline, case_start + CASE_SECONDS + 5)
        receipt = []
        calls = 0
        observed = False
        tool_ids = set()
        result = {}
        error = None
        cleanup = None
        state = None
        name = "refit-app-" + secrets.token_hex(10)
        proc = None
        if profile.instructions and setup["seam"] != "llm":
            return {"case": case["name"], "passed": False, "trace": [], "error": "native_instruction_seam_required",
                    "verdict": {"passed": False, "unsafe_attempts": 0}, "model_requests": 0}
        try:
            event("sandbox_starting", {"case": case["name"], "container": name})
            proc = subprocess.Popen(command(image_id, name), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, bufsize=0, env=env)
            os.set_blocking(proc.stdin.fileno(), False)
            os.set_blocking(proc.stdout.fileno(), False)
            runtime = native or setup
            args = runtime["args"]
            if profile.instructions:
                args = ["prompt", "--system", profile.instructions, *args[1:]]
            send(proc, {"files": snapshot["files"], "module": runtime.get("module"),
                        "entry": runtime.get("entry"), "args": args,
                        "model": model, "prompt": case["prompt"], "seam": runtime["seam"],
                        "timeout": CASE_SECONDS}, min(limit, time.monotonic() + 12))
            event("sandbox_started", {"case": case["name"], "phase": phase, "model": model, "container": name})
            buffer = bytearray()
            while True:
                check()
                now = time.monotonic()
                if now >= limit:
                    raise RunStopped("sandbox_timeout")
                try:
                    value = frame(proc, buffer, min(limit, now + 1))
                except TimeoutError:
                    continue
                if value.get("type") == "case":
                    result = value
                    break
                if value.get("type") != "completion":
                    raise ValueError("unexpected_worker_frame")
                body = value["body"]
                if (body.get("model") != model or body.get("stream", False) is not False
                        or body.get("tool_choice", "auto") not in ("auto", "none")):
                    raise ValueError("unsupported_model_request: use selected model, non-streaming chat and auto tools")
                messages = body["messages"]
                tools = body.get("tools")
                validate_completion({"model": model, "messages": messages, "tools": tools}, {model})
                if calls >= CASE_CALLS or broker.requests >= broker.max_requests:
                    raise RunStopped("inference_budget_exhausted")
                # The oracle checks the original tool observation, not only model prose.
                observed = observed or any(
                    msg.get("role") == "tool" and msg.get("tool_call_id") in tool_ids
                    and str(msg.get("content", "")).strip().strip('"') == case.get("tool_result")
                    for msg in messages
                )
                calls += 1
                requested_at = time.monotonic()
                event("inference_requested", {"model": model, "case": case["name"],
                                              "number": broker.requests + 1})
                options = {}
                if body.get("tool_choice") == "none":
                    options["tool_choice"] = "none"
                response_format = body.get("response_format")
                if response_format is not None:
                    if (not isinstance(response_format, dict)
                            or response_format.get("type") not in ("text", "json_object", "json_schema")
                            or len(json.dumps(response_format)) > 12_000):
                        raise ValueError("unsupported_model_request: invalid response format")
                    options["response_format"] = response_format
                message = broker.complete(model, messages, tools, max_tokens=512, **options)
                check()
                model_calls = message.get("tool_calls") or []
                tools_used = [x["function"]["name"] for x in model_calls]
                tool_ids.update(x["id"] for x in model_calls if x["function"]["name"] == case.get("tool"))
                inference = {"number": broker.requests, "model": model, "tools_called": tools_used,
                             "request_sha256": fingerprint(body), "response_sha256": fingerprint(message),
                             "seconds": round(time.monotonic() - requested_at, 3)}
                receipt.append(inference)
                event("inference_completed", inference)
                send(proc, {"message": message}, min(limit, time.monotonic() + 5))
            proc.wait(timeout=3)
            state = json.loads(subprocess.check_output(["docker", "inspect", name], timeout=5, env=env))[0]
            if proc.returncode != 0 or state["HostConfig"]["Runtime"] != "runsc" or state["State"]["OOMKilled"]:
                error = "sandbox_failed"
        except RunStopped as exc:
            error = str(exc)
        except Exception as exc:
            error = (str(exc)[:180] if isinstance(exc, RuntimeError) and
                     str(exc).startswith(("Vultr request returned HTTP", "model identity mismatch"))
                     else "sandbox_timeout" if isinstance(exc, TimeoutError)
                     else "unsupported_model_request" if str(exc).startswith("unsupported_model_request")
                     else "sandbox_or_provider_error")
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                proc.stdin.close()
                proc.stdout.close()
            cleanup = remove_and_verify("docker", name, env=env)
            event("sandbox_cleanup", {"case": case["name"], "phase": phase, "container": name, "receipt": cleanup})
        ok = (not error and result.get("status") == "completed" and result.get("exit_code") == 0
              and result.get("stdout", "").strip() == case["stdout"].strip()
              and (observed or "tool" not in case) and calls > 0 and cleanup["verified"])
        error = error or (None if ok else (
            "sandbox_cleanup_unverified" if not cleanup["verified"] else
            result.get("status") if result.get("status") != "completed" else
            "application_exited" if result.get("exit_code") != 0 else
            "model_boundary_unused" if calls == 0 else "outcome_mismatch"))
        verdict = {"passed": bool(ok), "unsafe_attempts": int(not cleanup["verified"]),
                   "stdout_matches": result.get("stdout", "").strip() == case["stdout"].strip(),
                   "required_tool_observed": observed if "tool" in case else None}
        evidence = {"case": case["name"], "passed": bool(ok), "verdict": verdict,
                    "error": error, "trace": receipt, "model_requests": calls,
                    "stdout_sha256": hashlib.sha256(result.get("stdout", "").encode()).hexdigest(),
                    "exit_code": result.get("exit_code"), "cleanup": cleanup,
                    "runtime": state["HostConfig"]["Runtime"] if state else None,
                    "oom_killed": state["State"]["OOMKilled"] if state else None,
                    "elapsed_seconds": round(time.monotonic() - case_start, 3)}
        event("case_completed", {**evidence, "phase": phase, "model": model})
        if error in {"cancelled", "run_timeout", "inference_budget_exhausted", "sandbox_timeout",
                     "sandbox_cleanup_unverified", "sandbox_or_provider_error"} or (error and error.startswith(
                         ("Vultr request returned HTTP", "model identity mismatch"))):
            raise RunStopped(error)
        return evidence

    contract = AgentContract("imported_application", (), (
        "Keep all native tools, existing instructions and business policies. Add only a short supplemental system instruction.",
        "Do not request changes to tool schemas or descriptions.",
    ))
    def split(name):
        return [ReplayCase(case["name"], case["prompt"],
            runner=lambda client, model, contract, profile, replay, c=case: execute(model, profile, c, name))
            for case in setup["cases"] if case["split"] == name]

    class RepairBroker:
        def complete(self, model, messages):
            check()
            if setup["seam"] != "llm":
                raise ValueError("A native instruction seam is required to apply and verify a repair.")
            event("inference_requested", {"model": model, "case": "repair", "number": broker.requests + 1})
            response = broker.complete(model, messages, max_tokens=900)
            event("inference_completed", {"model": model, "case": "repair", "number": broker.requests,
                                         "response_sha256": fingerprint(response)})
            return response

    report = migrate(RepairBroker(), contract, source, target, source, AgentProfile(""),
                     split("train"), lambda: split("validation"), lambda: split("holdout"),
                     progress=event)
    check()
    result = {"status": report["status"], "report": report, "export": None, "verification": []}
    if report["status"] in {"compatible_on_sample", "verified_adaptation"}:
        candidate = native_export(snapshot, setup, target, report.get("accepted_patch", {}).get("instructions", ""))
        # Read back exactly the serialized portable configuration. Each check
        # starts a fresh native process and a new isolated state directory.
        restored = json.loads(json.dumps(candidate))
        for case in setup["cases"]:
            if case["split"] == "holdout":
                result["verification"].append(execute(restored["model"], AgentProfile(restored["instructions"]),
                                                      case, "fresh_export", native=restored))
        if all(case["passed"] for case in result["verification"]):
            result["export"] = restored
        else:
            result["status"] = "export_failed_original_runner_verification"
    return result
