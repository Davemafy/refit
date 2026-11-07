"""Private operator application API. Bind to loopback behind SSH or HTTPS."""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import fcntl
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .api_service import ApiProblem
from .application_import import ARCHIVE_LIMIT, ImportProblem, github_archive, source_snapshot
from .application_run import BUDGET_LIMIT, MODELS, RunStopped, configuration, run_migration
from .docker_cleanup import remove_and_verify
from .durable_store import RunStore
from .refit_http import RefitHandler
from .refit_vultr_probe import VultrInference, load_key

ROOT = Path(__file__).resolve().parents[1]
BODY_LIMIT = ((ARCHIVE_LIMIT + 2) // 3) * 4 + 8192
ACTIVE = {"running", "cancelling"}


def now():
    return datetime.now(timezone.utc).isoformat()


class ApplicationService:
    def __init__(self, directory, token, image, daily_budget=24):
        if len(token) < 32:
            raise ValueError("Set a private REFIT_APPLICATION_TOKEN of at least 32 characters.")
        self.directory = directory
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.process_lock = (directory / ".service-lock").open("a")
        fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.token = token
        self.image = image
        self.daily_budget = daily_budget
        self.lock = threading.RLock()
        self.streams = threading.BoundedSemaphore(8)
        self.imports = {}
        self.runs = {}
        self.store = RunStore(directory / "runs")
        records, invalid = self.store.load()
        self.quarantined = bool(invalid)
        for run, events in records:
            self.runs[run["id"]] = (run, events)
            if run["status"] in ACTIVE:
                opened = {e["details"]["container"] for e in events if e["type"] == "sandbox_starting"}
                closed = {e["details"]["container"] for e in events if e["type"] == "sandbox_cleanup"
                          and e["details"]["receipt"]["verified"]}
                for container in sorted(opened - closed):
                    receipt = remove_and_verify("docker", container, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
                    self.emit(run["id"], "sandbox_cleanup", {"container": container, "receipt": receipt})
                run.update(status="interrupted", finished_at=now(), error="service_restarted")
                self.emit(run["id"], "terminal", {"status": run["status"]})
            if any(e["type"] == "sandbox_cleanup" and not e["details"]["receipt"]["verified"]
                   for e in events):
                self.quarantined = True

    def emit(self, ident, kind, details):
        with self.lock:
            run, events = self.runs[ident]
            if kind == "sandbox_cleanup" and not details["receipt"]["verified"]:
                self.quarantined = True
            if kind == "inference_requested":
                run["request_attempts_logged"] = details["number"]
            events.append({"seq": len(events) + 1, "type": kind, "message": kind,
                           "time": now(), "details": details})
            self.store.save(ident, run, events)

    def add_import(self, data):
        started = time.monotonic()
        if not isinstance(data, dict):
            raise ImportProblem("Provide an import object.")
        if data.get("method") == "github" and set(data) <= {"method", "repository", "revision", "token"}:
            repo, revision = data.get("repository"), data.get("revision")
            snapshot = source_snapshot(github_archive(repo, revision, data.get("token", "")), repo, revision)
        elif data.get("method") == "zip" and set(data) == {"method", "archive"}:
            try:
                archive = base64.b64decode(data["archive"], validate=True)
            except (ValueError, TypeError, binascii.Error) as exc:
                raise ImportProblem("Provide a base64-encoded project ZIP.") from exc
            snapshot = source_snapshot(archive)
        else:
            raise ImportProblem("Choose a pinned GitHub repository or a ZIP upload.")
        ident = "import-" + secrets.token_hex(8)
        summary = {k: v for k, v in snapshot.items() if k != "files"}
        summary.update(id=ident, file_count=len(snapshot["files"]),
                       import_seconds=round(time.monotonic() - started, 3))
        with self.lock:
            self.imports = {k: v for k, v in self.imports.items() if time.monotonic() - v[0] < 1800}
            if len(self.imports) >= 3:
                self.imports.pop(next(iter(self.imports)))
            self.imports[ident] = (time.monotonic(), snapshot, summary)
        return summary

    def start(self, data):
        if not isinstance(data, dict) or set(data) - {"import_id", "source", "target", "budget", "authorize", "setup"}:
            raise ApiProblem(422, "invalid_run", "Provide an import, two model identities, a budget and authorization.")
        source, target, budget = data.get("source"), data.get("target"), data.get("budget")
        if source not in MODELS or target not in MODELS or source == target:
            raise ApiProblem(422, "invalid_models", "Select two different available Vultr models.")
        if data.get("authorize") is not True or type(budget) is not int or not 1 <= budget <= BUDGET_LIMIT:
            raise ApiProblem(422, "budget_required", f"Authorize between 1 and {BUDGET_LIMIT} Vultr requests.")
        ident_import = data.get("import_id")
        if not isinstance(ident_import, str):
            raise ApiProblem(422, "import_required", "Inspect a source import first.")
        with self.lock:
            entry = self.imports.get(ident_import)
            if not entry or time.monotonic() - entry[0] >= 1800:
                raise ApiProblem(404, "import_expired", "Import the source again.")
            _, snapshot, summary = entry
            try:
                setup = configuration(snapshot, data.get("setup"))
            except ValueError as exc:
                raise ApiProblem(422, "setup_required", str(exc)) from exc
            if self.quarantined:
                raise ApiProblem(503, "operator_review_required", "Check persisted evidence and sandbox cleanup before starting another run.")
            if any(run["status"] in ACTIVE for run, _ in self.runs.values()):
                raise ApiProblem(409, "run_in_progress", "One application migration is already running.")
            day = now()[:10]
            reserved = sum(run["budget"] for run, _ in self.runs.values() if run["started_at"][:10] == day)
            if reserved + budget > self.daily_budget:
                raise ApiProblem(429, "daily_budget_exhausted", "This operator's daily request allowance is reserved.")
            try:
                broker = VultrInference(load_key(Path("/etc/refit/inference.env")), max_requests=budget)
            except (OSError, ValueError, RuntimeError) as exc:
                raise ApiProblem(503, "inference_unavailable", "Configure Vultr inference on the operator host.") from exc
            ident = "app-" + secrets.token_hex(8)
            run = {"id": ident, "mode": "application_live", "status": "running",
                   "started_at": now(), "source": source, "target": target, "budget": budget,
                   "import": summary, "model_requests": 0, "export": None}
            self.runs[ident] = (run, [])
            self.emit(ident, "run_started", {"source": source, "target": target, "budget": budget})
            self.imports.pop(ident_import)
            threading.Thread(target=self.execute, args=(ident, snapshot, setup, broker), daemon=True).start()
            return dict(run)

    def execute(self, ident, snapshot, setup, broker):
        started = time.monotonic()
        run, _ = self.runs[ident]
        try:
            result = run_migration(snapshot, setup, run["source"], run["target"], self.image,
                                   broker, lambda k, d: self.emit(ident, k, d),
                                   lambda: run["status"] == "cancelling")
        except RunStopped as exc:
            result = {"status": str(exc) if str(exc) in {"cancelled", "run_timeout", "inference_budget_exhausted"} else "failed",
                      "error": str(exc), "export": None}
        except Exception:
            result = {"status": "failed", "error": "runtime_unavailable_or_interrupted", "export": None}
        with self.lock:
            if run["status"] == "cancelling":
                result = {"status": "cancelled", "export": None}
            run.update(result, model_requests=broker.requests, finished_at=now(),
                       execution_seconds=round(time.monotonic() - started, 3))
            self.emit(ident, "terminal", {"status": run["status"], "model_requests": broker.requests})

    def get(self, ident):
        with self.lock:
            if ident not in self.runs:
                raise ApiProblem(404, "run_not_found", "No application run exists with this ID.")
            run, events = self.runs[ident]
            return dict(run), list(events)

    def cancel(self, ident):
        with self.lock:
            run, _ = self.get(ident)
            if run["status"] == "running":
                self.runs[ident][0]["status"] = "cancelling"
                self.emit(ident, "cancellation_requested", {})
            return self.get(ident)[0]


class ApplicationHandler(RefitHandler):
    service: ApplicationService

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def authorize(self):
        token = self.headers.get("Authorization", "")
        if not secrets.compare_digest(token.encode(), ("Bearer " + self.service.token).encode()):
            raise ApiProblem(401, "operator_access_required", "Provide the operator access token.")

    def body(self):
        value = self.headers.get("Content-Length", "")
        if not value.isascii() or not value.isdecimal() or len(value) > 8 or not 1 <= int(value) <= BODY_LIMIT:
            raise ApiProblem(413, "body_limit", "The request exceeds the upload limit.")
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiProblem(415, "json_required", "Use application/json.")
        return json.loads(self.rfile.read(int(value)))

    def do_HEAD(self):
        self._send(404, {"error": {"code": "not_found"}})

    def do_POST(self):
        try:
            self.authorize()
            path = urlsplit(self.path).path
            if path == "/api/application/imports":
                if not self.service.streams.acquire(blocking=False):
                    raise ApiProblem(429, "operator_busy", "Try the import again when a connection closes.")
                try:
                    return self._send(201, self.service.add_import(self.body()))
                finally:
                    self.service.streams.release()
            if path == "/api/application/runs":
                return self._send(202, self.service.start(self.body()))
            match = re.fullmatch(r"/api/application/runs/(app-[0-9a-f]{16})/cancel", path)
            if match:
                return self._send(200, self.service.cancel(match[1]))
            raise ApiProblem(404, "not_found", "This application route does not exist.")
        except ApiProblem as exc:
            self._problem(exc)
        except (ImportProblem, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._problem(ApiProblem(422, "import_or_request_invalid", str(exc)[:300]))
        except socket.timeout:
            self._problem(ApiProblem(408, "request_timeout", "The request did not finish in time."))

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            if url.path in ("/", "/bring"):
                body = (ROOT / "web" / "application" / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)
                return
            self.authorize()
            if url.path == "/api/application":
                return self._send(200, {"models": MODELS, "max_requests": BUDGET_LIMIT})
            match = re.fullmatch(r"/api/application/runs/(app-[0-9a-f]{16})(/events|/artifact|/evidence)?", url.path)
            if not match:
                raise ApiProblem(404, "not_found", "This application route does not exist.")
            ident, route = match.groups()
            run, events = self.service.get(ident)
            if route == "/artifact":
                if run["export"] is None:
                    raise ApiProblem(409, "artifact_withheld", "This run has no verified export.")
                return self._send(200, run["export"])
            if route == "/evidence":
                return self._send(200, {"run": run, "events": events})
            if route == "/events":
                value = parse_qs(url.query).get("after", ["0"])[0]
                if not re.fullmatch(r"[0-9]{1,7}", value):
                    raise ApiProblem(422, "invalid_cursor", "Use a nonnegative event cursor.")
                return self.events(ident, int(value))
            return self._send(200, {key: val for key, val in run.items() if key not in {"report", "export"}}
                              | {"export_available": run["export"] is not None})
        except ApiProblem as exc:
            self._problem(exc)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return

    def events(self, ident, cursor):
        if not self.service.streams.acquire(blocking=False):
            raise ApiProblem(429, "stream_limit", "Too many active event streams.")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                run, events = self.service.get(ident)
                for event in events[cursor:]:
                    self.wfile.write(f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n".encode())
                    cursor = event["seq"]
                self.wfile.flush()
                if run["status"] not in ACTIVE:
                    return
                time.sleep(0.35)
        finally:
            self.service.streams.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--image", default="refit-application")
    parser.add_argument("--daily-budget", type=int, choices=range(1, 97), default=24)
    args = parser.parse_args()
    service = ApplicationService(args.state, os.getenv("REFIT_APPLICATION_TOKEN", ""), args.image, args.daily_budget)
    handler = type("Handler", (ApplicationHandler,), {"service": service})
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
