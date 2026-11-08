"""Application-native execution through the existing gVisor and Vultr boundaries."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time

from .container_agent import command, frame, send, validate_completion
from .application_oracle import evaluate, evaluate_state, matches_tool_arguments, validate_case
from .docker_cleanup import remove_and_verify
from .migration_engine import AgentContract, AgentProfile, ReplayCase, fingerprint, migrate
from .refit_vultr_probe import ENDPOINT

MODELS = ("deepseek-v4.1-flash-1017", "glm-5.2")
BUDGET_LIMIT = 64
CASE_SECONDS = 100
RUN_SECONDS = 1000
CASE_CALLS = 8
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
    if isinstance(supplied, dict) and ("entry" in supplied) != ("module" in supplied):
        runtime = "typescript" if "entry" in supplied else "python"
    if runtime not in {"python", "typescript"}:
        raise ValueError("Choose a discovered application or supply an explicit Python module or Node CLI.")
    key = "entry" if runtime == "typescript" else "module"
    required = {key, "args", "cases"}
    optional_seam = {"instruction_env", "instruction_base"}
    if isinstance(supplied, dict):
        supplied = dict(supplied)
        if supplied.pop("format", "refit.agent.v1") != "refit.agent.v1":
            raise ValueError("Use application contract format refit.agent.v1.")
        if supplied.pop("mode", "managed") != "managed":
            raise ValueError("This server executes managed applications. Use a managed contract.")
    supplied_keys = set(supplied) if isinstance(supplied, dict) else set()
    if not required <= supplied_keys or supplied_keys - required - {"provider_env"} not in (set(), optional_seam):
        raise ValueError(snapshot["discovery"]["setup"] or "Provide an entry, arguments and evaluation cases.")
    if "provider_env" in supplied_keys and supplied["provider_env"] not in ("openai", "generic"):
        raise ValueError("Choose the OpenAI-prefixed or generic Chat Completions environment variables.")
    if optional_seam <= supplied_keys:
        instruction_env = supplied["instruction_env"]
        instruction_base = supplied["instruction_base"]
        if (not isinstance(instruction_env, str) or
                not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}_(?:PROMPT|INSTRUCTIONS)", instruction_env)):
            raise ValueError("Use an explicit, nonprivileged existing instruction environment variable.")
        if (not isinstance(instruction_base, str) or not 1 <= len(instruction_base) <= 4096
                or "\x00" in instruction_base):
            raise ValueError("Provide the original application instruction text, without changes.")
    entry, args, cases = (supplied[name] for name in (key, "args", "cases"))
    if runtime == "typescript":
        if (not isinstance(entry, str) or entry not in snapshot["files"]
                or not entry.endswith((".ts", ".mts", ".js", ".mjs"))
                or entry.endswith(".d.ts")):
            raise ValueError("Choose a TypeScript or JavaScript CLI file present in the imported source.")
        manifest = next((str(parent / "package.json") for parent in PurePosixPath(entry).parents
                         if str(parent / "package.json") in snapshot["files"]), None)
        if manifest is None:
            raise ValueError("TypeScript execution is unavailable without a package.json declaring its runtime dependencies.")
        try:
            package = json.loads(base64.b64decode(snapshot["files"][manifest]))
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
    validate_application_cases(cases)
    return {**supplied, "seam": "instruction-env" if optional_seam <= supplied_keys else "openai-env"}


def validate_application_cases(cases):
    if not isinstance(cases, list) or not 3 <= len(cases) <= 6:
        raise ValueError("Provide 3 to 6 cases covering train, validation and holdout.")
    names = set()
    prompts = set()
    for case in cases:
        validate_case(case)
        if case["name"] in names or case["prompt"] in prompts:
            raise ValueError("Give each case a unique name and prompt.")
        names.add(case["name"])
        prompts.add(case["prompt"])
    if {case["split"] for case in cases} != {"train", "validation", "holdout"}:
        raise ValueError("Each split needs at least one independent case.")


def native_export(snapshot, setup, model, instructions=""):
    config = {"format": "refit.application-export.v1", "model": model,
              "source_sha256": snapshot["source_sha256"], "repository": snapshot["repository"],
              "revision": snapshot["revision"], "args": setup["args"],
              **{key: setup[key] for key in ("entry", "module") if key in setup},
              "instructions": instructions, "seam": setup["seam"]}
    if setup.get("local_python"):
        config["execution_mode"] = "local_connector"
        config["python"] = setup["local_python"]
    if setup.get("test_service"):
        config["execution_mode"] = "existing_test_service"
        config["test_service"] = setup["test_service"]
    if snapshot.get("snapshot_sha256"):
        config["snapshot_sha256"] = snapshot["snapshot_sha256"]
    if snapshot.get("directory"):
        config["directory"] = snapshot["directory"]
    if setup["seam"] == "instruction-env":
        config["instruction_env"] = setup["instruction_env"]
        config["instruction_base"] = setup["instruction_base"]
    if setup["seam"] == "llm":
        config["extra-openai-models.yaml"] = [{"model_id": model, "model_name": model,
            "api_base": ENDPOINT.removesuffix("/chat/completions"), "api_key_name": "vultr",
            "can_stream": False, "supports_tools": True}]
    else:
        config["environment"] = {"OPENAI_MODEL": model,
            "OPENAI_BASE_URL": ENDPOINT.removesuffix("/chat/completions")}
        if setup.get("provider_env") == "generic":
            config["provider_env"] = "generic"
            config["environment"] = {"MODEL": model, "BASE_URL": ENDPOINT.removesuffix("/chat/completions")}
            config["credential_env"] = "API_KEY"
        if setup["seam"] == "instruction-env":
            config["environment"][setup["instruction_env"]] = (
                setup["instruction_base"] +
                ("\n\n" + instructions if instructions else ""))
    config["integrity_sha256"] = fingerprint(config)
    return config


def read_only_tool_signature(message):
    """Hash a repeated identical read-only tool action without retaining arguments.

    Repeated calls are diagnostic, not grounds for changing the native
    application's behavior or bypassing independent verification.
    """
    calls = message.get("tool_calls") or []
    if (not isinstance(calls, list) or not calls or
            any(not isinstance(call, dict) or not isinstance(call.get("function"), dict)
                or call["function"].get("name") not in {"read_file", "list_files"}
                for call in calls)):
        return None
    normalized = []
    for call in calls:
        fn = call["function"]
        arguments = fn.get("arguments")
        if not isinstance(arguments, str):
            return None
        try:
            parsed = json.loads(arguments)
        except (ValueError, TypeError):
            return None
        normalized.append((fn["name"], parsed))
    return fingerprint(normalized)


def completion_tool_choice(body, tools):
    """Preserve the original agent's choice, limited to its declared functions."""
    choice = body.get("tool_choice", "auto")
    if choice in ("auto", "none") or (choice == "required" and tools):
        return choice
    if (isinstance(choice, dict) and set(choice) == {"type", "function"}
            and choice["type"] == "function" and isinstance(choice["function"], dict)
            and set(choice["function"]) == {"name"} and isinstance(choice["function"]["name"], str)
            and any(isinstance(tool, dict) and tool.get("type") == "function"
                    and isinstance(tool.get("function"), dict)
                    and tool["function"].get("name") == choice["function"]["name"]
                    for tool in tools or ())):
        return choice
    raise ValueError("unsupported_model_request: select an available function or use auto, none, or required")



def run_migration(snapshot, setup, source, target, image, broker, event, stopped, *, local_python=None, test_service=None, service_bearer=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    started = time.monotonic()
    local = local_python is not None or test_service is not None
    if local:
        if local_python is not None and (not setup.get("module") or not os.path.isabs(local_python) or not os.access(local_python, os.X_OK)):
            raise ValueError("Local connector requires a Python module and an absolute executable interpreter.")
        if test_service is not None:
            if local_python is not None or not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}/[A-Za-z0-9/_-]+", test_service):
                raise ValueError("Service connector accepts only an explicitly authorized loopback HTTP endpoint.")
            if not isinstance(service_bearer, str) or not re.fullmatch(r"[!-~]{16,512}", service_bearer):
                raise ValueError("Set a scoped service bearer token.")
            if any(case.get("state") for case in setup["cases"]):
                raise ValueError("File-state checks are unavailable for service execution.")
            setup = {**setup, "test_service": test_service}
        else:
            setup = {**setup, "local_python": local_python}
        runtime_label = "existing_test_service" if test_service else "local_connector"
        worker = Path(__file__).resolve().parents[1] / "integrations/application/worker.py"
        event("runtime_ready", {"runtime": runtime_label, "isolation": "developer_host"})
    else:
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
        all_tool_calls = []
        last_read_only_signature = None
        consecutive_read_only_calls = 0
        result = {}
        error = None
        cleanup = None
        state = None
        name = "refit-app-" + secrets.token_hex(10)
        proc = None
        local_state = None
        if profile.instructions and setup["seam"] not in ("llm", "instruction-env"):
            return {"case": case["name"], "passed": False, "trace": [], "error": "native_instruction_seam_required",
                    "verdict": {"passed": False, "unsafe_attempts": 0}, "model_requests": 0}
        try:
            if local:
                local_state = tempfile.TemporaryDirectory(prefix="refit-local-")
                argv = [sys.executable, "-I", "-B", "-u", str(worker), "--local-connector"]
                worker_env = {**env, "TMPDIR": local_state.name}
            else:
                event("sandbox_starting", {"case": case["name"], "container": name})
                argv = command(image_id, name)
                worker_env = env
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, bufsize=0, env=worker_env,
                                    start_new_session=local)
            os.set_blocking(proc.stdin.fileno(), False)
            os.set_blocking(proc.stdout.fileno(), False)
            runtime = native or setup
            args = runtime["args"]
            if profile.instructions and setup["seam"] == "llm":
                args = ["prompt", "--system", profile.instructions, *args[1:]]
            state_paths = sorted({check["path"] for check in case.get("state", [])})
            send(proc, {"local_python": runtime.get("python", local_python),
                        "test_service": runtime.get("test_service", test_service),
                        "service_bearer": service_bearer, "state_paths": state_paths, "files": snapshot["files"], "module": runtime.get("module"),
                        "entry": runtime.get("entry"), "args": args, "provider_env": runtime.get("provider_env"),
                        "model": model, "prompt": case["prompt"], "seam": runtime["seam"],
                        "instruction_env": runtime.get("instruction_env"),
                        "instruction_base": runtime.get("instruction_base"),
                        "instructions": profile.instructions,
                        "timeout": CASE_SECONDS}, min(limit, time.monotonic() + 12))
            event("local_started" if local else "sandbox_started",
                  {"case": case["name"], "phase": phase, "model": model,
                   **({"container": name} if not local else {})})
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
                if body.get("model") != model or body.get("stream", False) is not False:
                    raise ValueError("unsupported_model_request: use selected model and non-streaming chat")
                messages = body["messages"]
                tools = body.get("tools")
                validate_completion({"model": model, "messages": messages, "tools": tools}, {model})
                tool_choice = completion_tool_choice(body, tools)
                if calls >= CASE_CALLS:
                    raise RunStopped("case_request_limit_exhausted")
                if broker.requests >= broker.max_requests:
                    raise RunStopped("inference_budget_exhausted")
                # The oracle checks the original tool observation, not only model prose.
                for msg in messages:
                    if msg.get("role") != "tool" or msg.get("tool_call_id") not in tool_ids:
                        continue
                    if "tool_result" not in case or (
                            str(msg.get("content", "")).strip().strip('"') == case["tool_result"]):
                        observed = True
                calls += 1
                requested_at = time.monotonic()
                event("inference_requested", {"model": model, "case": case["name"],
                                              "number": broker.requests + 1})
                options = {}
                if tool_choice != "auto":
                    options["tool_choice"] = tool_choice
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
                signature = read_only_tool_signature(message)
                if signature is None:
                    last_read_only_signature = None
                    consecutive_read_only_calls = 0
                elif signature == last_read_only_signature:
                    consecutive_read_only_calls += 1
                else:
                    last_read_only_signature = signature
                    consecutive_read_only_calls = 1
                if consecutive_read_only_calls == 4:
                    event("repeated_read_only_tool_calls", {
                        "model": model, "case": case["name"], "phase": phase,
                        "consecutive": consecutive_read_only_calls,
                        "signature_sha256": signature,
                        "meaning": "Repeated identical read-only calls; execution continues within its budget.",
                    })
                all_tool_calls.extend(tools_used)
                tool_ids.update(
                    x["id"] for x in model_calls if x["function"]["name"] == case.get("tool")
                    and matches_tool_arguments(case, x["function"].get("arguments"))
                )
                inference = {"number": broker.requests, "model": model, "tools_called": tools_used,
                             "repeated_read_only_call_count": consecutive_read_only_calls,
                             "request_sha256": fingerprint(body), "response_sha256": fingerprint(message),
                             "seconds": round(time.monotonic() - requested_at, 3)}
                receipt.append(inference)
                event("inference_completed", inference)
                send(proc, {"message": message}, min(limit, time.monotonic() + 5))
            proc.wait(timeout=3)
            if local:
                if proc.returncode != 0:
                    error = "local_worker_failed"
            else:
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
                if local:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                proc.stdin.close()
                proc.stdout.close()
            if local:
                if local_state is not None:
                    local_state.cleanup()
                cleanup = {"verified": local_state is not None and not os.path.lexists(local_state.name),
                           "scope": "connector_temporary_workspace_and_worker_process",
                           "isolation": "developer_host"}
                event("local_cleanup", {"case": case["name"], "phase": phase, "receipt": cleanup})
            else:
                cleanup = remove_and_verify("docker", name, env=env)
                event("sandbox_cleanup", {"case": case["name"], "phase": phase, "container": name, "receipt": cleanup})
        outcome = evaluate(case, result.get("stdout", ""), all_tool_calls, observed,
                           tool_arguments_observed=observed)
        state_checks = evaluate_state(case.get("state", []), result.get("state", {}))
        ok = (all(check["passed"] for check in state_checks) and not error and result.get("status") == "completed" and result.get("exit_code") == 0
              and outcome["passed"] and calls > 0 and cleanup["verified"])
        error = error or (None if ok else (
            "sandbox_cleanup_unverified" if not cleanup["verified"] else
            result.get("status") if result.get("status") != "completed" else
            "application_exited" if result.get("exit_code") != 0 else
            "model_boundary_unused" if calls == 0 else "outcome_mismatch"))
        verdict = {"passed": bool(ok), "unsafe_attempts": int(not cleanup["verified"]),
                   "stdout_matches": outcome["stdout_matches"],
                   "json_matches": outcome["json_matches"],
                   "required_tool_called": outcome["required_tool_called"],
                   "required_tool_observed": (
                       outcome["required_tool_observed"] if "tool_result" in case
                       else outcome["required_tool_called"]),
                   "forbidden_tools_absent": outcome["forbidden_tools_absent"],
                   "tool_arguments_match": outcome["tool_arguments_match"],
                   **({"state_checks_passed": all(check["passed"] for check in state_checks)}
                      if state_checks else {})}
        evidence = {"case": case["name"], "passed": bool(ok), "verdict": verdict,
                    "error": error, "trace": receipt, "model_requests": calls,
                    "repeated_read_only_calls": consecutive_read_only_calls,
                    "state_checks": state_checks,
                    "stdout_sha256": hashlib.sha256(result.get("stdout", "").encode()).hexdigest(),
                    "exit_code": result.get("exit_code"), "cleanup": cleanup,
                    "worker_transport_exit_code": proc.returncode if proc is not None else None,
                    "runtime": runtime_label if local else state["HostConfig"]["Runtime"] if state else None,
                    "oom_killed": state["State"]["OOMKilled"] if state else None,
                    "elapsed_seconds": round(time.monotonic() - case_start, 3)}
        event("case_completed", {**evidence, "phase": phase, "model": model,
                                 "adapted": bool(profile.instructions)})
        if error in {"cancelled", "run_timeout", "inference_budget_exhausted",
                     "case_request_limit_exhausted", "sandbox_timeout",
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
            if setup["seam"] not in ("llm", "instruction-env"):
                raise ValueError("An explicit native instruction seam is required for a repair.")
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
