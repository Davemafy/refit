"""HTTP route verification for account-gated model-written diagnostics."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.application_http import ApplicationHandler, ApplicationService, now

ORIGIN = "https://refit.example"
RUN_ID = "app-aaaaaaaaaaaaaaaa"
REPORT = {
    "source_training": {"passed": 2, "total": 2, "failed": []},
    "target_training": {"passed": 1, "total": 2, "failed": ["x"]},
}


class DiagnosticHttpTests(unittest.TestCase):
    def test_real_http_owner_origin_and_reject_arbitrary_code(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
                "REFIT_ENABLE_SANDBOX_DIAGNOSTICS": "1",
                "REFIT_SANDBOX_RUNTIME": "runsc"}):
            service = ApplicationService(
                Path(directory), "test-operator-token-32-characters",
                "image", public_origin=ORIGIN)
            session = service.accounts.register("http-owner", "test-only password")
            owner = service.accounts.resolve(session)[0]
            cookie = "__Host-refit-session=" + session
            run = {"id": RUN_ID, "mode": "application_live",
                   "status": "candidate_failed_validation", "owner": owner,
                   "started_at": now(), "finished_at": now(),
                   "source": "deepseek-v4.1-flash-1017", "target": "glm-5.2",
                   "budget": 2, "model_requests": 2,
                   "report": REPORT, "export": None}
            service.runs[RUN_ID] = (run, [])
            handler = type("Handler", (ApplicationHandler,), {"service": service})
            with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()

                def send(method, path, data=None, session_cookie=cookie, origin=ORIGIN):
                    client = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
                    try:
                        body = json.dumps(data) if data is not None else None
                        client.request(method, "/api/application/runs/" + RUN_ID + path,
                                       body, {"Content-Type": "application/json",
                                              "X-Refit-Public": "1",
                                              "Cookie": session_cookie, "Origin": origin})
                        resp = client.getresponse()
                        return resp.status, json.loads(resp.read())
                    finally:
                        client.close()

                try:
                    self.assertEqual(send("POST", "/diagnose", {}, origin="https://other.example")[0], 403)
                    self.assertEqual(send("POST", "/diagnose", {}, session_cookie="")[0], 401)
                    self.assertEqual(send("POST", "/diagnose", {"code": "print(1)"})[0], 422)
                    self.assertTrue(send("GET", "")[1]["diagnostics_available"])
                    original_start = Thread.start
                    def allow_server_only(worker):
                        if getattr(getattr(worker, "_target", None), "__name__", "") == "_execute_diagnostic":
                            return None
                        return original_start(worker)
                    with patch.object(ApplicationService, "broker",
                                      return_value=SimpleNamespace(requests=0)), \
                         patch("scripts.application_http.threading.Thread.start", new=allow_server_only):
                        status, reply = send("POST", "/diagnose", {})
                    self.assertEqual(status, 202)
                    self.assertEqual(reply["status"], "running")
                    self.assertEqual(send("POST", "/diagnose", {})[1]["error"]["code"],
                                     "diagnostic_already_requested")
                finally:
                    server.shutdown()
                    thread.join(timeout=4)
                    service.process_lock.close()


if __name__ == "__main__":
    unittest.main()
