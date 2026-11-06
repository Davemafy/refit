"""Refit API application state and guarded migration orchestration.

Zero external dependencies. Only trusted, built-in adapters may execute.
This is NOT an untrusted-code sandbox and must not be exposed as one.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Any

from .refit_vultr_probe import VultrInference, load_key
from .compatibility_artifact import create_receipt, validate_and_load
from .durable_store import RunStore
from .release_identity import capture_revision
from . import refund_adapter, deployment_incident_probe


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORDINGS = ROOT / "data" / "recorded"
ALLOWED_MODELS = (
    "deepseek-v4.1-flash-1017",
    "muse-glimmer-30b",
    "raon-1-mini-preview",
)
DOMAINS = {"refund": refund_adapter, "deployment": deployment_incident_probe}
MODEL_ALIASES = {
    "deepseek": "deepseek-v4.1-flash-1017",
    "muse": "muse-glimmer-30b",
    "glimmer": "muse-glimmer-30b",
    "raon": "raon-1-mini-preview",
}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


def read_json_file(path: Path) -> dict:
    record = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(record, dict):
        raise ValueError("stored run must be an object")
    return record


def interpret(text: str) -> dict:
    """Conservative text-to-typed-intent; never execute user-supplied code.

    This is NOT unrestricted model-agent import or a general LLM planner.
    Ambiguous requests return missing fields instead of guessing.
    """
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200:
        raise ApiProblem(422, "invalid_text", "Describe the migration in 1–1200 characters.")
    lower = text.lower()
    domain_hits = {
        "refund": bool(re.search(r"\b(refund|order|customer support|customer-support)\b", lower)),
        "deployment": bool(re.search(r"\b(deployment|rollback|incident|release|service)\b", lower)),
    }
    domains = [name for name, matched in domain_hits.items() if matched]
    domain = domains[0] if len(domains) == 1 else None
    mentions: list[tuple[int, str]] = []
    for alias, full_name in MODEL_ALIASES.items():
        match = re.search(r"\b" + re.escape(alias) + r"\b", lower)
        if match:
            mentions.append((match.start(), full_name))
    # Deduplicate a name mentioned by multiple aliases.
    ordered_models = []
    for _, model in sorted(mentions):
        if model not in ordered_models:
            ordered_models.append(model)
    source = ordered_models[0] if len(ordered_models) >= 2 else None
    target = ordered_models[1] if len(ordered_models) >= 2 else None
    if len(ordered_models) == 1:
        # "migrate to X" identifies a target, not an assumed source.
        model = ordered_models[0]
        before = lower[:next(pos for pos, m in sorted(mentions) if m == model)]
        if re.search(r"\b(to|into|use|switch to|move to)\s*$", before):
            target = model
        elif re.search(r"\b(from|currently on|using)\s*$", before):
            source = model
    missing = [k for k, value in (
        ("domain", domain), ("source_model", source), ("target_model", target)
    ) if value is None]
    return {
        "intent": "model_migration",
        "domain": domain,
        "source_model": source,
        "target_model": target,
        "missing": missing,
        "ready_for_review": not missing and source != target,
        "requires_confirmation": True,
        "supported_external_agents": False,
        "message": (
            "Review these options before running. Only two built-in agent "
            "workflows are currently supported; this does not import your agent."
        ),
    }


class RunService:
    def __init__(self, recordings_dir: Path = DEFAULT_RECORDINGS,
                 runs_dir: Path | None = None, live_enabled: bool = False,
                 run_token: str = "", daily_limit: int = 3,
                 max_requests: int = 160,
                 executor: ThreadPoolExecutor | None = None):
        if daily_limit < 1 or not 1 <= max_requests <= 400:
            raise ValueError("invalid run budget")
        self.recordings_dir = Path(recordings_dir)
        self.release_revision = capture_revision(ROOT)
        self.runs_dir = Path(runs_dir) if runs_dir else None
        self.live_enabled = live_enabled
        self.run_token = run_token
        self.daily_limit = daily_limit
        self.max_requests = max_requests
        self.lock = threading.Lock()
        self.active: str | None = None
        self.started_dates: list[str] = []
        self.runs: dict[str, dict] = {}
        self.events: dict[str, list[dict]] = {}
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="refit")
        self._load_recordings()
        self.recovery_warnings = []
        self._restore_runs()

    def _load_recordings(self):
        if not self.recordings_dir.is_dir():
            raise FileNotFoundError(f"recordings directory missing: {self.recordings_dir}")
        for path in sorted(self.recordings_dir.glob("*.json")):
            if path.name.endswith(".artifact.json"):
                continue
            run = read_json_file(path)
            id_ = run.get("id")
            if not isinstance(id_, str) or not re.fullmatch(r"[a-z0-9-]+", id_):
                raise ValueError("invalid recorded run identifier")
            if run.get("mode") != "recorded" or run.get("domain") not in DOMAINS:
                raise ValueError("invalid recorded run mode/domain")
            if run.get("source") not in ALLOWED_MODELS or run.get("target") not in ALLOWED_MODELS:
                raise ValueError("recorded run has unsupported model")
            if id_ in self.runs:
                raise ValueError("duplicate recorded run id")
            self.runs[id_] = run
            self.events[id_] = [{"seq": 1, "type": "recorded", "at": "2026-11-06",
                                 "message": "Imported from a verified historical run"}]

    def _restore_runs(self):
        if self.runs_dir is None:
            return
        records, warnings = RunStore(self.runs_dir).load()
        self.recovery_warnings.extend(warnings)
        changed = []
        for run, events in records:
            run_id = run["id"]
            if (run_id in self.runs or run.get("domain") not in DOMAINS or
                    run.get("source") not in ALLOWED_MODELS or
                    run.get("target") not in ALLOWED_MODELS):
                self.recovery_warnings.append(run_id)
                continue
            if not events:
                events = [{"seq": 1, "type": "restored",
                           "message": "Legacy run restored without earlier events.",
                           "at": timestamp()}]
            self.runs[run_id] = run
            self.events[run_id] = events
            created = run.get("created_at")
            if isinstance(created, str) and re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", created[:10]):
                self.started_dates.append(created[:10])
            if run["status"] in ("queued", "running"):
                run["status"] = "execution_interrupted"
                run["finished_at"] = timestamp()
                run["patch"] = None
                run["error"] = {
                    "code": "worker_interrupted",
                    "message": "Server restarted during evaluation. Not retried or approved.",
                }
                self._emit(run_id, "interrupted",
                           "Run interrupted by restart; no automatic inference retry.")
                changed.append(run_id)
        for run_id in changed:
            self._persist(run_id)

    def health(self) -> dict:
        return {"status": "ok", "service": "refit", "contract_version": "v1",
                "revision": dict(self.release_revision)}

    def capabilities(self) -> dict:
        return {
            "contract_version": "v1",
            "domains": list(DOMAINS),
            "models": list(ALLOWED_MODELS),
            "recorded_runs": True,
            "durable_run_history": self.runs_dir is not None,
            "recovery_warnings": len(self.recovery_warnings),
            "live_runs_enabled": bool(self.live_enabled and self.run_token),
            "external_agent_import": False,
            "sandbox": {
                "integrated": False,
                "business_tools_sandbox_configured": (
                    os.getenv("REFIT_USE_TOOL_SANDBOX") == "1"
                ),
                "business_tools_isolated": False,
                "business_tools_isolation_verified_on_vultr_vm": False,
                "generated_python_diagnostics_enabled": (
                    os.getenv("REFIT_ENABLE_SANDBOX_DIAGNOSTICS") == "1"
                ),
                "runtime": (
                    os.getenv("REFIT_SANDBOX_RUNTIME", "runsc")
                    if os.getenv("REFIT_ENABLE_SANDBOX_DIAGNOSTICS") == "1"
                    else None
                ),
            },
            "warnings": [
                "Only built-in, synthetic business workflows are currently supported.",
                "Live runs are disabled unless explicitly configured and authenticated.",
                "This API does not provide secure execution of arbitrary agent code.",
                "Sandboxed tool replay supports only two reviewed built-in agent environments.",
            ],
        }

    def list_runs(self) -> list[dict]:
        with self.lock:
            return [{
                "id": r["id"], "mode": r["mode"], "domain": r["domain"],
                "source": r["source"], "target": r["target"],
                "status": r["status"], "evidence_url": r.get("evidence_url"),
                "created_at": r.get("created_at"),
            } for r in sorted(
                self.runs.values(),
                key=lambda item: (item.get("created_at") or "", item["id"]),
                reverse=True,
            )]

    def get_run(self, run_id: str) -> dict:
        with self.lock:
            result = self.runs.get(run_id)
            if result is None:
                raise ApiProblem(404, "run_not_found", "The requested run does not exist.")
            return json.loads(json.dumps(result))

    def get_artifact(self, run_id: str) -> dict:
        record = self.get_run(run_id)
        if record.get("status") != "verified_adaptation":
            raise ApiProblem(404, "artifact_not_found",
                             "This run did not produce a verified compatibility patch.")
        if record["mode"] == "recorded":
            filename = record.get("artifact_filename", "")
            if not re.fullmatch(r"[a-z0-9-]+\.artifact\.json", filename):
                raise ApiProblem(404, "artifact_not_found",
                                 "No compatibility artifact was archived for this run.")
            artifact = read_json_file(self.recordings_dir / filename)
        else:
            artifact = record.get("patch")
        if not isinstance(artifact, dict):
            raise ApiProblem(404, "artifact_not_found",
                             "No verified compatibility artifact is available.")
        adapter = DOMAINS[record["domain"]]
        # Reject altered or mismatched artifacts before serving them.
        validate_and_load(artifact, adapter.CONTRACT, adapter.BASE_PROFILE, record["target"])
        return artifact

    def get_events(self, run_id: str, after: int = 0) -> dict:
        with self.lock:
            if run_id not in self.runs:
                raise ApiProblem(404, "run_not_found", "The requested run does not exist.")
            events = [dict(item) for item in self.events[run_id] if item["seq"] > after]
            return {"run_id": run_id, "events": events,
                    "next_after": self.events[run_id][-1]["seq"] if self.events[run_id] else 0,
                    "terminal": self.runs[run_id]["status"] not in ("queued", "running")}

    def _emit(self, run_id: str, type_: str, message: str,
              details: dict | None = None):
        series = self.events[run_id]
        event = {"seq": len(series) + 1, "type": type_,
                 "message": message, "at": timestamp()}
        if details is not None:
            event["details"] = details
        series.append(event)

    def _progress(self, run_id: str, event_type: str, details: dict) -> None:
        """Persist measured stage events, never guessed progress percentages."""
        if event_type not in (
            "phase_started", "phase_completed", "repair_started", "repair_generated"
        ):
            raise ValueError("unsupported progress event")
        allowed = {"phase", "model", "passed", "total", "unsafe_attempts",
                   "repair_model", "candidate_variants"}
        if set(details) - allowed or any(
                not isinstance(value, (str, int)) or type(value) is bool
                for value in details.values()):
            raise ValueError("invalid progress payload")
        phase = str(details.get("phase", "repair"))
        if event_type == "phase_started":
            message = "Evaluating " + phase.replace("_", " ") + "."
        elif event_type == "phase_completed":
            message = (
                "Evaluated " + phase.replace("_", " ") + ": " +
                str(details["passed"]) + "/" + str(details["total"]) + " passed."
            )
        elif event_type == "repair_started":
            message = "Generating a bounded compatibility repair."
        else:
            message = "Repair proposal generated; evaluating candidates."
        with self.lock:
            self._emit(run_id, event_type, message, details)
            self.runs[run_id]["current_phase"] = phase
        if self.runs_dir:
            self._persist(run_id)

    def _submit_durably(self, run_id: str, day: str, fn, *args) -> None:
        """No paid worker launch without an on-disk queued event."""
        try:
            if self.runs_dir:
                self._persist(run_id)
        except (OSError, ValueError, TypeError):
            with self.lock:
                self.runs.pop(run_id, None)
                self.events.pop(run_id, None)
                if self.active == run_id:
                    self.active = None
                self.started_dates.remove(day)
            raise ApiProblem(503, "persistence_unavailable",
                             "Cannot start a live run without durable storage.")
        try:
            self.executor.submit(fn, *args)
        except Exception:
            with self.lock:
                self.runs[run_id]["status"] = "execution_error"
                self.runs[run_id]["finished_at"] = timestamp()
                self._emit(run_id, "failed", "Worker scheduling failed.")
                if self.active == run_id:
                    self.active = None
            if self.runs_dir:
                self._persist(run_id)
            raise ApiProblem(503, "worker_unavailable", "Could not start live worker.")

    def start(self, data: Any, bearer: str) -> dict:
        if not self.live_enabled or not self.run_token:
            raise ApiProblem(503, "live_disabled", "Live inference is disabled; use a recorded run.")
        if not hmac.compare_digest(bearer, self.run_token):
            raise ApiProblem(401, "authentication_required",
                             "Live runs require an operator access token.")
        required = {"domain", "source_model", "target_model"}
        if not isinstance(data, dict) or set(data) != required:
            raise ApiProblem(422, "invalid_request",
                             "Provide only domain, source_model, and target_model.")
        domain, source, target = (data["domain"], data["source_model"], data["target_model"])
        if domain not in DOMAINS or source not in ALLOWED_MODELS or target not in ALLOWED_MODELS:
            raise ApiProblem(422, "unsupported_config", "Unsupported agent workflow or model.")
        if source == target:
            raise ApiProblem(422, "same_model", "Source and target must differ.")
        day = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            self.started_dates = [d for d in self.started_dates if d == day]
            if self.active is not None:
                raise ApiProblem(409, "run_in_progress", "Another live migration is already running.")
            if len(self.started_dates) >= self.daily_limit:
                raise ApiProblem(429, "daily_limit", "Daily live-run allowance reached.")
            run_id = "live-" + secrets.token_hex(8)
            run = {
                "id": run_id, "mode": "live", "domain": domain,
                "engine_revision": dict(self.release_revision),
                "source": source, "target": target,
                "status": "queued", "created_at": timestamp(),
                "execution_isolation": "none",
                "report": None, "patch": None,
            }
            self.runs[run_id] = run
            self.events[run_id] = []
            self._emit(run_id, "queued", "Live migration accepted.")
            self.active = run_id
            self.started_dates.append(day)
        self._submit_durably(run_id, day, self._execute, run_id)
        return {"id": run_id, "status": "queued", "events_url": f"/api/runs/{run_id}/events"}

    def start_diagnostic(self, source_run_id: str, bearer: str) -> dict:
        # Reuse actual archived migration evidence; never allow arbitrary
        # uploaded code, custom repository URLs, or model selection.
        if os.getenv("REFIT_ENABLE_SANDBOX_DIAGNOSTICS") != "1":
            raise ApiProblem(503, "sandbox_disabled",
                             "Live sandbox diagnostics are not enabled.")
        if not self.live_enabled or not self.run_token:
            raise ApiProblem(503, "live_disabled", "Live inference is disabled.")
        if not hmac.compare_digest(bearer, self.run_token):
            raise ApiProblem(401, "authentication_required",
                             "Live diagnostics require an operator token.")
        source = self.get_run(source_run_id)
        if source.get("mode") != "recorded":
            raise ApiProblem(422, "recorded_run_required",
                             "This diagnostic accepts verified archived runs only.")
        day = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            self.started_dates = [x for x in self.started_dates if x == day]
            if self.active is not None:
                raise ApiProblem(409, "run_in_progress", "Another live task is running.")
            if len(self.started_dates) >= self.daily_limit:
                raise ApiProblem(429, "daily_limit", "Daily live-run allowance reached.")
            run_id = "diagnostic-" + secrets.token_hex(8)
            self.runs[run_id] = {
                "id": run_id, "mode": "live_diagnostic",
                "domain": source["domain"], "source": source["source"],
                "target": source["target"], "status": "queued",
                "source_run_id": source_run_id, "created_at": timestamp(),
                "report": None, "patch": None,
                "execution_isolation": "generated_code_only",
            }
            self.events[run_id] = []
            self._emit(run_id, "queued", "Sandbox diagnosis queued.")
            self.active = run_id
            self.started_dates.append(day)
        self._submit_durably(run_id, day, self._execute_diagnostic, run_id, source)
        return {
            "id": run_id, "status": "queued",
            "events_url": f"/api/runs/{run_id}/events",
        }

    def _execute_diagnostic(self, run_id: str, source: dict):
        with self.lock:
            self.runs[run_id]["status"] = "running"
            self._emit(run_id, "started", "Vultr model generating a diagnostic program.")
        try:
            if self.runs_dir:
                self._persist(run_id)
            from .sandbox_diagnostics import generate_and_verify
            from .sandbox_runner import DockerSandbox
            client = VultrInference(
                load_key(Path("/etc/refit/inference.env")), max_requests=1
            )
            runtime = os.getenv("REFIT_SANDBOX_RUNTIME", "runsc")
            diagnostic = generate_and_verify(
                source, client, "deepseek-v4.1-flash-1017",
                DockerSandbox(runtime=runtime),
            )
            with self.lock:
                record = self.runs[run_id]
                record["sandbox_diagnostic"] = diagnostic
                record["model_requests"] = client.requests
                record["status"] = (
                    "diagnostic_verified" if diagnostic["verified"]
                    else "diagnostic_failed"
                )
                record["finished_at"] = timestamp()
                self._emit(
                    run_id, "complete" if diagnostic["verified"] else "failed",
                    "Isolated diagnostic verified against the host oracle."
                    if diagnostic["verified"] else
                    "Diagnostic or sandbox failed independent verification.",
                )
        except Exception as exc:
            with self.lock:
                record = self.runs[run_id]
                record["status"] = "diagnostic_failed"
                record["error"] = {
                    "code": type(exc).__name__,
                    "message": "Sandbox diagnostic failed; archived migration is unchanged.",
                }
                record["finished_at"] = timestamp()
                self._emit(run_id, "failed", "Sandbox diagnostic could not finish.")
        finally:
            with self.lock:
                if self.active == run_id:
                    self.active = None
            if self.runs_dir:
                self._persist(run_id)

    def _execute(self, run_id: str):
        with self.lock:
            record = self.runs[run_id]
            record["status"] = "running"
            self._emit(run_id, "started", "Evaluating with live Vultr inference.")
            domain, source, target = record["domain"], record["source"], record["target"]
        try:
            if self.runs_dir:
                self._persist(run_id)
            # Fixed vetted adapters only; business isolation needs explicit
            # gVisor configuration and host-specific verification.
            client = VultrInference(
                load_key(Path("/etc/refit/inference.env")),
                max_requests=self.max_requests,
            )
            seed = secrets.randbelow(2_000_000_000)
            with self.lock:
                record["evaluation_seed"] = seed
            if self.runs_dir:
                self._persist(run_id)
            progress = lambda event, details: self._progress(run_id, event, details)
            if os.getenv("REFIT_USE_TOOL_SANDBOX") == "1":
                from .sandbox_tool_gateway import migrate_in_tool_sandboxes
                result = migrate_in_tool_sandboxes(
                    client, domain, source, target, source, seed,
                    runtime=os.getenv("REFIT_SANDBOX_RUNTIME", "runsc"),
                    progress=progress,
                )
            else:
                result = DOMAINS[domain].run_live(
                    client, source, target, source, seed=seed,
                    progress=progress,
                )
            # A migration verdict is not releasable if its requested sandbox
            # boundary was missing or cleanup could not be independently checked.
            if os.getenv("REFIT_USE_TOOL_SANDBOX") == "1":
                boundary = result.get("execution_boundary") or {}
                if (boundary.get("runtime") !=
                        os.getenv("REFIT_SANDBOX_RUNTIME", "runsc") or
                        boundary.get("business_tools_isolated") is not True or
                        boundary.get("all_containers_removed") is not True or
                        type(boundary.get("worker_runs")) is not int or
                        boundary["worker_runs"] < 1):
                    raise RuntimeError("sandbox containment evidence incomplete")
            accepted = (
                create_receipt(
                    result, DOMAINS[domain].CONTRACT,
                    DOMAINS[domain].BASE_PROFILE, source, target
                )
                if result.get("status") == "verified_adaptation" else None
            )
            diagnostic = None
            if os.getenv("REFIT_ENABLE_SANDBOX_DIAGNOSTICS") == "1":
                # A separate, genuine Vultr model response writes Python.
                # This is supplementary diagnosis, NEVER the business oracle.
                try:
                    from .sandbox_diagnostics import generate_and_verify
                    from .sandbox_runner import DockerSandbox
                    runtime = os.getenv("REFIT_SANDBOX_RUNTIME", "runsc")
                    diagnostic = generate_and_verify(
                        {"domain": domain, "report": result},
                        client, source, DockerSandbox(runtime=runtime)
                    )
                except Exception as exc:
                    diagnostic = {
                        "kind": "vultr_model_generated_python_diagnostic",
                        "verified": False, "error_code": type(exc).__name__,
                        "message": "Isolated code diagnosis failed; migration outcome unchanged."
                    }
            with self.lock:
                record["report"] = result
                boundary = result.get("execution_boundary") or {}
                record["execution_isolation"] = (
                    "docker_tool_sandbox_verified_cleanup"
                    if boundary.get("business_tools_isolated")
                    and boundary.get("all_containers_removed")
                    else "none"
                )
                record["patch"] = accepted
                if diagnostic is not None:
                    record["sandbox_diagnostic"] = diagnostic
                    self._emit(
                        run_id, "sandbox_diagnostic",
                        "Generated code executed and independently verified in a sandbox."
                        if diagnostic.get("verified")
                        else "Sandbox diagnosis did not pass verification."
                    )
                record["model_requests"] = client.requests
                record["status"] = result["status"]
                record["finished_at"] = timestamp()
                self._emit(run_id, "complete", "Migration evaluation finished.")
        except Exception:
            # Never expose secrets or model-provider error bodies in public API.
            with self.lock:
                record["status"] = "execution_error"
                record["error"] = {
                    "code": "evaluation_failed",
                    "message": "Live evaluation failed. View a recorded run or ask the operator."
                }
                record["finished_at"] = timestamp()
                self._emit(run_id, "failed", "The evaluation could not complete.")
        finally:
            with self.lock:
                if self.active == run_id:
                    self.active = None
            if self.runs_dir:
                self._persist(run_id)

    def _persist(self, run_id: str):
        """Atomically save the complete state and resumable event cursor."""
        if not self.runs_dir:
            return
        with self.lock:
            run = json.loads(json.dumps(self.runs[run_id]))
            events = json.loads(json.dumps(self.events[run_id]))
        RunStore(self.runs_dir).save(run_id, run, events)
