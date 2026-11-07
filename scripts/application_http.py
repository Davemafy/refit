"""Private operator application API. Bind to loopback behind SSH or HTTPS."""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import fcntl
import gzip
from http.cookies import CookieError, SimpleCookie
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
from .application_accounts import Accounts, SESSION_TTL
from .application_import import ARCHIVE_LIMIT, ImportProblem, github_archive, source_snapshot
from .application_run import BUDGET_LIMIT, MODELS, RunStopped, configuration, run_migration
from .docker_cleanup import remove_and_verify
from .durable_store import RunStore
from .migration_engine import fingerprint
from .refit_http import RefitHandler
from .refit_vultr_probe import VultrInference, load_key

ROOT = Path(__file__).resolve().parents[1]
BODY_LIMIT = ((ARCHIVE_LIMIT + 2) // 3) * 4 + 8192
ACTIVE = {"running", "cancelling"}
ACCOUNT_BUDGET = 16
COOKIE = "__Host-refit-session"


def reserved_requests(run):
    # Interrupted jobs keep the whole reservation because an in-flight
    # provider call may have outlived the process.
    if run["status"] in ACTIVE or run["status"] == "interrupted":
        return run["budget"]
    return max(run.get("model_requests", run["budget"]), run.get("request_attempts_logged", 0))


def now():
    return datetime.now(timezone.utc).isoformat()


DEMO_ID = "demo-python-2026-11-07"


def public_example():
    """Allowlisted, previously verified migration evidence only.

    Never serialize live user runs, raw imported source, private tool outputs,
    model prompts, auth state, or privileged sandbox/host receipts.
    """
    path = ROOT / "data/evaluations/application-browser-generic-2026-11-07.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        original = json.load(stream)
    source = original["run"]
    result = {key: source.get(key) for key in (
        "status", "started_at", "finished_at", "source", "target",
        "budget", "model_requests", "execution_seconds"
    )}
    result.update(
        id=DEMO_ID, demo=True, export_available=bool(source.get("export")),
        import_={"discovery": {"runtime": "python"}},
    )
    result["import"] = result.pop("import_")
    result["verification"] = [
        {"case": check.get("case"), "passed": check.get("passed")}
        for check in source.get("verification", [])
    ]
    events = []
    allowed = {"run_started", "runtime_ready", "phase_started",
               "phase_completed", "sandbox_started", "sandbox_cleanup",
               "inference_requested", "inference_completed",
               "case_completed", "terminal"}
    for event in original["events"]:
        kind = event.get("type")
        if kind not in allowed:
            continue
        detail = event.get("details", {})
        fields = ("case", "phase", "model", "passed", "error",
                  "stdout_sha256", "number", "tools_called", "status",
                  "total", "seconds")
        sanitized = {key: detail[key] for key in fields if key in detail}
        if kind == "case_completed":
            verdict = detail.get("verdict", {})
            sanitized["verdict"] = {
                "required_tool_observed": verdict.get("required_tool_observed")
            }
        if kind == "sandbox_cleanup":
            sanitized["receipt"] = {
                "verified": bool(detail.get("receipt", {}).get("verified"))
            }
        events.append({
            "seq": event.get("seq"),
            "type": kind,
            "time": event.get("time"),
            "details": sanitized,
        })
    export = source.get("export")
    artifact = None
    if isinstance(export, dict):
        allowed_export = ("format", "model", "source_sha256", "module",
                          "args", "instructions", "seam", "environment",
                          "integrity_sha256")
        artifact = {key: export[key] for key in allowed_export if key in export}
    return {"run": result, "events": events, "artifact": artifact,
            "recorded": True, "public_sample": True}


class ApplicationService:
    def __init__(self, directory, token, image, daily_budget=24, public_origin=None):
        if len(token) < 32:
            raise ValueError("Set a private REFIT_APPLICATION_TOKEN of at least 32 characters.")
        self.directory = directory
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.process_lock = (directory / ".service-lock").open("a")
        fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.token = token
        self.public_origin = public_origin
        self.accounts = Accounts(directory) if public_origin else None
        self.account_slots = threading.BoundedSemaphore(2)
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

    def add_import(self, data, owner="operator"):
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
                       file_paths=sorted(snapshot["files"])[:160],
                       file_paths_truncated=len(snapshot["files"]) > 160,
                       import_seconds=round(time.monotonic() - started, 3))
        if owner != "operator":
            self.accounts.save_project(owner, ident, summary, snapshot)
            return summary
        with self.lock:
            self.imports = {k: v for k, v in self.imports.items() if time.monotonic() - v[0] < 1800}
            if len(self.imports) >= 3:
                self.imports.pop(next(iter(self.imports)))
            self.imports[ident] = (time.monotonic(), snapshot, summary)
        return summary

    def start(self, data, owner="operator"):
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
            if owner == "operator":
                entry = self.imports.get(ident_import)
                if not entry or time.monotonic() - entry[0] >= 1800:
                    raise ApiProblem(404, "import_expired", "Import the source again.")
                _, snapshot, summary = entry
            else:
                project = self.accounts.project(owner, ident_import)
                if not project:
                    raise ApiProblem(404, "import_not_found", "No project exists with this ID.")
                snapshot, summary = project
            try:
                setup = configuration(snapshot, data.get("setup"))
            except ValueError as exc:
                raise ApiProblem(422, "setup_required", str(exc)) from exc
            if self.quarantined:
                raise ApiProblem(503, "operator_review_required", "Check persisted evidence and sandbox cleanup before starting another run.")
            if any(run["status"] in ACTIVE for run, _ in self.runs.values()):
                raise ApiProblem(409, "run_in_progress", "One application migration is already running.")
            day = now()[:10]
            reserved = sum(reserved_requests(run) for run, _ in self.runs.values() if run["started_at"][:10] == day)
            own_reserved = sum(reserved_requests(run) for run, _ in self.runs.values()
                               if run.get("owner") == owner and run["started_at"][:10] == day)
            if owner != "operator" and own_reserved + budget > ACCOUNT_BUDGET:
                raise ApiProblem(429, "account_budget_exhausted", "Your daily request allowance is reserved.")
            if reserved + budget > self.daily_budget:
                raise ApiProblem(429, "daily_budget_exhausted", "This operator's daily request allowance is reserved.")
            try:
                broker = VultrInference(load_key(Path("/etc/refit/inference.env")), max_requests=budget)
            except (OSError, ValueError, RuntimeError) as exc:
                raise ApiProblem(503, "inference_unavailable", "Configure Vultr inference on the operator host.") from exc
            ident = "app-" + secrets.token_hex(8)
            run = {"id": ident, "mode": "application_live", "status": "running",
                   "started_at": now(), "source": source, "target": target, "budget": budget,
                   "owner": owner, "import": summary, "model_requests": 0, "export": None,
                   "configuration_sha256": fingerprint({"source": source, "target": target, "budget": budget,
                       "source_sha256": snapshot["source_sha256"], "setup": setup})}
            self.runs[ident] = (run, [])
            self.emit(ident, "run_started", {"source": source, "target": target, "budget": budget})
            if owner == "operator":
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

    def get(self, ident, owner=None):
        with self.lock:
            if ident not in self.runs or (owner is not None and
                    self.runs[ident][0].get("owner", "operator") != owner):
                raise ApiProblem(404, "run_not_found", "No application run exists with this ID.")
            run, events = self.runs[ident]
            return dict(run), list(events)

    def cancel(self, ident, owner="operator"):
        with self.lock:
            run, _ = self.get(ident, owner)
            if run["status"] == "running":
                self.runs[ident][0]["status"] = "cancelling"
                self.emit(ident, "cancellation_requested", {})
            return self.get(ident, owner)[0]


class ApplicationHandler(RefitHandler):
    service: ApplicationService

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def public(self):
        return self.service.accounts is not None and self.headers.get("X-Refit-Public") == "1"

    def session_secret(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        return cookies[COOKIE].value if COOKIE in cookies else ""

    def authorize(self):
        if self.public():
            session = self.service.accounts.resolve(self.session_secret())
            if session is None:
                raise ApiProblem(401, "sign_in_required", "Sign in to use your Refit workspace.")
            return session[0]
        token = self.headers.get("Authorization", "")
        if not secrets.compare_digest(token.encode(), ("Bearer " + self.service.token).encode()):
            raise ApiProblem(401, "operator_access_required", "Provide the operator access token.")
        return "operator"

    def end_headers(self):
        if getattr(self, "_session_cookie", None):
            self.send_header("Set-Cookie", self._session_cookie)
        super().end_headers()

    def account_action(self, path):
        accounts = self.service.accounts
        if path.endswith("/logout"):
            accounts.logout(self.session_secret())
            self._session_cookie = f"{COOKIE}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0"
            return self._send(200, {"signed_in": False})
        if not self.service.account_slots.acquire(blocking=False):
            raise ApiProblem(429, "auth_busy", "Try signing in again in a moment.")
        try:
            data = self.body(limit=2048)
            registering = path.endswith("/register")
            fields = {"username", "password", "invite"} if registering else {"username", "password"}
            if not isinstance(data, dict) or set(data) != fields:
                raise ValueError("Provide the required account fields.")
            secret = accounts.register(**data) if registering else accounts.login(**data)
        except ValueError as exc:
            raise ApiProblem(400 if registering else 401, "account_rejected", str(exc)) from None
        finally:
            self.service.account_slots.release()
        self._session_cookie = (f"{COOKIE}={secret}; Path=/; Secure; HttpOnly; SameSite=Strict; "
                                f"Max-Age={SESSION_TTL}")
        return self._send(201 if registering else 200, {"signed_in": True, "username": data["username"]})

    def body(self, limit=BODY_LIMIT):
        value = self.headers.get("Content-Length", "")
        if not value.isascii() or not value.isdecimal() or len(value) > 8 or not 1 <= int(value) <= limit:
            raise ApiProblem(413, "body_limit", "The request exceeds the upload limit.")
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiProblem(415, "json_required", "Use application/json.")
        return json.loads(self.rfile.read(int(value)))

    def do_HEAD(self):
        self._send(404, {"error": {"code": "not_found"}})

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if self.public():
                if self.headers.get("Origin") != self.service.public_origin:
                    raise ApiProblem(403, "origin_rejected", "Open the HTTPS Refit workspace to make changes.")
                if path in ("/api/application/register", "/api/application/login", "/api/application/logout"):
                    return self.account_action(path)
            owner = self.authorize()
            if path == "/api/application/imports":
                if not self.service.streams.acquire(blocking=False):
                    raise ApiProblem(429, "operator_busy", "Try the import again when a connection closes.")
                try:
                    return self._send(201, self.service.add_import(self.body(), owner))
                finally:
                    self.service.streams.release()
            if path == "/api/application/runs":
                return self._send(202, self.service.start(self.body(), owner))
            match = re.fullmatch(r"/api/application/runs/(app-[0-9a-f]{16})/cancel", path)
            if match:
                return self._send(200, self.service.cancel(match[1], owner))
            project = re.fullmatch(r"/api/application/projects/(import-[0-9a-f]{16})/remove", path)
            if project and owner != "operator" and self.service.accounts.remove_project(owner, project[1]):
                return self._send(200, {"removed": True})
            raise ApiProblem(404, "not_found", "This application route does not exist.")
        except ApiProblem as exc:
            self._problem(exc)
        except (ValueError, UnicodeDecodeError) as exc:
            self._problem(ApiProblem(422, "import_or_request_invalid", str(exc)[:300]))
        except socket.timeout:
            self._problem(ApiProblem(408, "request_timeout", "The request did not finish in time."))

    def send_page(self, filename, mime):
        body = (ROOT / "web" / "application" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            page = url.path
            # Fixed-allowlist assets, never arbitrary file paths or user source.
            assets = {
                "/assets/ui.css": ("ui.css", "text/css; charset=utf-8"),
                "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/assets/auth.js": ("auth.js", "text/javascript; charset=utf-8"),
            }
            if page in assets:
                filename, mime = assets[page]
                return self.send_page(filename, mime)
            if page == "/bring" and self.public():
                return self.redirect("/app/agents/new")
            page_files = {
                "/": "landing.html", "/docs": "docs.html",
                "/login": "auth.html", "/signup": "auth.html",
                "/bring": "index.html",  # Preserve operator-only test harness.
                "/app": "app.html", "/app/agents": "app.html",
                "/app/agents/new": "app.html", "/app/runs": "app.html",
                "/app/evidence": "app.html", "/app/settings": "app.html",
            }
            filename = page_files.get(page)
            if filename is None and (page == "/app/runs/" + DEMO_ID or
                                     re.fullmatch(r"/app/runs/app-[0-9a-f]{16}", page)):
                filename = "app.html"
            if filename is not None:
                # Browsing requires a session, but ownership enforcement always
                # remains on the API and applies to every request.
                return self.send_page(filename, "text/html; charset=utf-8")
            if url.path == "/api/application/demo" and self.public():
                return self._send(200, public_example())
            if url.path == "/api/application/session":
                if not self.public():
                    return self._send(200, {"mode": "operator"})
                session = self.service.accounts.resolve(self.session_secret())
                return self._send(200, {"mode": "account", "username": session[1] if session else None})
            owner = self.authorize()
            if url.path == "/api/application":
                return self._send(200, {"models": MODELS,
                    "max_requests": BUDGET_LIMIT if owner == "operator" else ACCOUNT_BUDGET})
            if url.path == "/api/application/projects" and owner != "operator":
                return self._send(200, {"projects": self.service.accounts.list_projects(owner)})
            if url.path == "/api/application/runs":
                with self.service.lock:
                    runs = [{k: run.get(k) for k in ("id", "status", "started_at", "source", "target")}
                            for run, _ in reversed(list(self.service.runs.values()))
                            if run.get("owner", "operator") == owner][:50]
                return self._send(200, {"runs": runs})
            match = re.fullmatch(r"/api/application/runs/(app-[0-9a-f]{16})(/events|/artifact|/evidence)?", url.path)
            if not match:
                raise ApiProblem(404, "not_found", "This application route does not exist.")
            ident, route = match.groups()
            run, events = self.service.get(ident, owner)
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
                return self.events(ident, int(value), owner)
            return self._send(200, {key: val for key, val in run.items() if key not in {"report", "export"}}
                              | {"export_available": run["export"] is not None})
        except ApiProblem as exc:
            self._problem(exc)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return

    def events(self, ident, cursor, owner):
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
                run, events = self.service.get(ident, owner)
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
    parser.add_argument("--public-origin", default=os.getenv("REFIT_PUBLIC_ORIGIN"))
    args = parser.parse_args()
    if args.public_origin and not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?", args.public_origin):
        parser.error("Public origin must be an exact HTTPS origin.")
    service = ApplicationService(args.state, os.getenv("REFIT_APPLICATION_TOKEN", ""),
                                 args.image, args.daily_budget, args.public_origin)
    handler = type("Handler", (ApplicationHandler,), {"service": service})
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
