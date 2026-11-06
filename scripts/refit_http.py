"""Refit JSON HTTP gateway for an independently developed frontend.

Use a same-origin reverse proxy for the UI. No cross-origin API access is
enabled. This server does not execute uploaded code and is not a sandbox.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .api_service import ApiProblem, RunService


class RefitHandler(BaseHTTPRequestHandler):
    service: RunService

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _problem(self, problem: ApiProblem):
        self._send(problem.status, {"error": {"code": problem.code,
                                              "message": problem.detail}})

    def _json_body(self):
        length = self.headers.get("Content-Length")
        if not length or not length.isascii() or not length.isdecimal():
            raise ApiProblem(400, "invalid_body", "JSON body and Content-Length are required.")
        size = int(length)
        if not 1 <= size <= 4096:
            raise ApiProblem(413, "body_too_large", "JSON requests must be at most 4 KiB.")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise ApiProblem(415, "unsupported_media_type", "Use application/json.")
        raw = self.rfile.read(size)
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ApiProblem(400, "invalid_json", "The request body must be valid JSON.")
        return parsed

    def do_GET(self):
        try:
            parts = urlsplit(self.path)
            path = parts.path
            if path == "/api/health":
                return self._send(200, self.service.health())
            if path == "/api/capabilities":
                return self._send(200, self.service.capabilities())
            if path == "/api/runs":
                return self._send(200, {"runs": self.service.list_runs()})
            match = re.fullmatch(r"/api/runs/([a-z0-9-]+)(/events|/artifact)?", path)
            if match:
                run_id, suffix = match.groups()
                if suffix == "/artifact":
                    return self._send(200, self.service.get_artifact(run_id))
                if suffix == "/events":
                    query = parse_qs(parts.query)
                    if set(query) - {"after"}:
                        raise ApiProblem(422, "invalid_cursor", "Only the after cursor is supported.")
                    raw = query.get("after", ["0"])[0]
                    if not raw.isdecimal() or len(raw) > 8:
                        raise ApiProblem(422, "invalid_cursor", "after must be a nonnegative integer.")
                    return self._send(200, self.service.get_events(run_id, int(raw)))
                return self._send(200, self.service.get_run(run_id))
            raise ApiProblem(404, "not_found", "No API route exists at this path.")
        except ApiProblem as problem:
            self._problem(problem)

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path == "/api/interpret":
                data = self._json_body()
                if not isinstance(data, dict) or set(data) != {"text"}:
                    raise ApiProblem(422, "invalid_request", "Provide only a text field.")
                from .api_service import interpret
                return self._send(200, interpret(data["text"]))
            if path == "/api/runs":
                data = self._json_body()
                authorization = self.headers.get("Authorization", "")
                bearer = authorization[len("Bearer "):] if authorization.startswith("Bearer ") else ""
                return self._send(201, self.service.start(data, bearer))
            raise ApiProblem(404, "not_found", "No API route exists at this path.")
        except ApiProblem as problem:
            self._problem(problem)

    def do_OPTIONS(self):
        self._send(405, {"error": {"code": "cross_origin_disabled",
                                   "message": "The Refit API is same-origin only."}})

    def log_message(self, format, *args):
        # Avoid untrusted request URLs and Authorization header contents in
        # application logs; the reverse proxy may keep its own access logs.
        pass


def make_handler(service: RunService):
    class Handler(RefitHandler):
        pass
    Handler.service = service
    return Handler


def main():
    ap = argparse.ArgumentParser(description="Refit demo API (built-in workflows only)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument("--runs-dir", type=Path, default=Path("/var/lib/refit/runs"))
    args = ap.parse_args()
    service = RunService(
        runs_dir=args.runs_dir,
        live_enabled=os.getenv("REFIT_ENABLE_LIVE") == "1",
        run_token=os.getenv("REFIT_RUN_TOKEN", ""),
        daily_limit=int(os.getenv("REFIT_DAILY_LIVE_RUNS", "3")),
        max_requests=int(os.getenv("REFIT_MAX_REQUESTS_PER_RUN", "160")),
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    print(f"Refit API listening at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
