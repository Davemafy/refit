"""Temporary local HTTPS fixture for browser UX acceptance. NEVER deploy.

All paid migration submissions are denied. Historical migration evidence
comes from an archived real run, only for testing the review UI.
"""
import gzip
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from scripts.api_service import ApiProblem
from scripts.application_http import ApplicationHandler, ApplicationService


class FixtureHandler(ApplicationHandler):
    def public(self):
        return True  # This isolated HTTPS fixture stands in for Nginx ingress.

    def do_POST(self):
        if urlsplit(self.path).path == "/api/application/runs":
            return self._problem(ApiProblem(429, "test_inference_disabled", "Live inference is disabled in UI tests."))
        return super().do_POST()

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ("/__fixture__/seed", "/__fixture__/seed-failure"):
            owner = self.authorize()
            with gzip.open("data/evaluations/application-browser-generic-2026-11-07.json.gz", "rt") as source:
                archived = json.load(source)
            run, events = archived["run"].copy(), archived["events"]
            run["id"] = "app-" + secrets.token_hex(8)
            run["owner"] = owner
            if route == "/__fixture__/seed-failure":
                # UI-only adversarial fixture; not a real migration or production endpoint.
                run["status"] = "failed"
                run["export"] = None
                run["verification"] = []
                run["report"] = None
                run["error"] = "required_tool_missing"
                events = json.loads(json.dumps(events))
                changed = 0
                for event in events:
                    if (event["type"] == "case_completed"
                            and event.get("details", {}).get("phase") == "train"
                            and event["details"].get("model") == run["target"]
                            and changed == 0):
                        event["details"]["passed"] = False
                        event["details"]["verdict"]["stdout_matches"] = False
                        event["details"]["verdict"]["required_tool_observed"] = False
                        event["details"]["error"] = "required_tool_missing"
                        changed += 1
                    if event["type"] == "terminal":
                        event["details"]["status"] = "failed"
                assert changed == 1
            with self.service.lock:
                self.service.runs[run["id"]] = (run, events)
                self.service.store.save(run["id"], run, events)
            return self._send(200, {"id": run["id"], "status": run["status"]})
        return super().do_GET()


def main():
    with tempfile.TemporaryDirectory(prefix="refit-ui-fixture-") as temp:
        cert, key = Path(temp)/"cert.pem", Path(temp)/"key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-keyout", str(key), "-out", str(cert),
                        "-subj", "/CN=localhost"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        service = ApplicationService(Path(temp), "fixture-operator-token-32characters", "disabled",
                                     public_origin="https://localhost:8873")
        handler = type("Handler", (FixtureHandler,), {"service": service})
        server = ThreadingHTTPServer(("127.0.0.1", 8873), handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(cert), keyfile=str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        print("REFIT_FIXTURE_READY=" + json.dumps({"url":"https://localhost:8873"}), flush=True)
        try:
            server.serve_forever()
        finally:
            server.shutdown()
            service.process_lock.close()


if __name__ == "__main__":
    main()
