"""Ownership checks through the real HTTP routing layer, with zero inference."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from scripts.application_http import ApplicationHandler, ApplicationService, now

ORIGIN = "https://refit.example"
PASSWORD = "a test-only password"


class ApplicationAccountTests(unittest.TestCase):
    def test_operator_can_configure_larger_bounded_quotas_without_authorization_loss(self):
        with TemporaryDirectory() as directory:
            service = ApplicationService(
                Path(directory), "test-operator-token-32-characters", "image",
                daily_budget=512, public_origin=ORIGIN, account_budget=96
            )
            self.assertEqual(service.account_budget, 96)
            self.assertEqual(service.daily_budget, 512)
            secret = service.accounts.register("engineer", "example-password-12345")
            owner = service.accounts.resolve(secret)[0]
            self.assertTrue(owner)
            self.assertNotEqual(owner, "operator")
            self.assertEqual(service.account_budget, 96)
            service.process_lock.close()
        for daily, own in ((0, 16), (2049, 16), (72, 0), (72, 513)):
            with self.subTest(daily=daily, account=own), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, "bounded"):
                    ApplicationService(
                        Path(directory), "test-operator-token-32-characters", "image",
                        daily_budget=daily, public_origin=ORIGIN, account_budget=own
                    )

    def test_account_ownership_session_origin_and_budget(self):
        with TemporaryDirectory() as directory:
            service = ApplicationService(Path(directory), "test-operator-token-32-characters", "image",
                                         daily_budget=48, public_origin=ORIGIN)
            handler = type("Handler", (ApplicationHandler,), {"service": service})
            with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()

                def request(method, path, data=None, cookie="", origin=ORIGIN):
                    client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    try:
                        client.request(method, "/api/application" + path,
                            json.dumps(data) if data is not None else None,
                            {"Content-Type": "application/json", "X-Refit-Public": "1",
                             "Cookie": cookie, "Origin": origin})
                        response = client.getresponse()
                        return response.status, json.loads(response.read()), response.getheader("Set-Cookie")
                    finally:
                        client.close()

                try:
                    payload = {"username": "alice", "password": PASSWORD}
                    self.assertEqual(request("POST", "/register", payload, origin="https://other.example")[0], 403)
                    status, _, cookie = request("POST", "/register", payload)
                    self.assertEqual(status, 201)
                    for flag in ("Secure", "HttpOnly", "SameSite=Strict"):
                        self.assertIn(flag, cookie)
                    alice = cookie.split(";", 1)[0]
                    self.assertEqual(request("POST", "/register", payload)[0], 400)
                    self.assertEqual(request("POST", "/register", {**payload, "username": "extra", "invite": "unused"})[0], 400)
                    status, _, cookie = request("POST", "/register", {
                        **payload, "username": "bob"})
                    self.assertEqual(status, 201)
                    bob = cookie.split(";", 1)[0]
                    self.assertEqual(request("GET", "/projects")[0], 401)
                    status, capability, _ = request("GET", "", cookie=alice)
                    self.assertEqual(status, 200)
                    self.assertEqual(capability["max_requests"], 16)
                    self.assertEqual(capability["account_daily_allowance"], 16)
                    self.assertEqual(capability["global_daily_ceiling"], 48)
                    owner = service.accounts.resolve(alice.split("=", 1)[1])[0]
                    project = "import-1234567890abcdef"
                    service.accounts.save_project(owner, project, {"id": project},
                        {"discovery": {"preset": "llm-0.37.1"}, "source_sha256": "test", "files": {}})
                    run_id = "app-1234567890abcdef"
                    run = {"id": run_id, "status": "compatible_on_sample", "mode": "application_live",
                           "owner": owner, "budget": 16, "started_at": now(),
                           "export": {"model": "test"}}
                    service.runs[run_id] = (run, [])
                    self.assertEqual(request("GET", "/projects", cookie=bob)[1]["projects"], [])
                    self.assertEqual(request("GET", "/runs", cookie=bob)[1]["runs"], [])
                    self.assertEqual(request("GET", "/projects", cookie=alice)[1]["projects"][0]["id"], project)
                    self.assertEqual(request("GET", f"/runs/{run_id}/artifact", cookie=alice)[0], 200)
                    for route in ("", "/events", "/evidence", "/artifact"):
                        self.assertEqual(request("GET", f"/runs/{run_id}{route}", cookie=bob)[0], 404)
                    self.assertEqual(request("POST", f"/runs/{run_id}/cancel", {}, bob)[0], 404)
                    self.assertEqual(request("POST", f"/projects/{project}/remove", {}, bob)[0], 404)
                    start = {"import_id": project, "source": "deepseek-v4.1-flash-1017",
                             "target": "glm-5.2", "budget": 1, "authorize": True}
                    self.assertEqual(request("POST", "/runs", start, bob)[0], 404)
                    self.assertEqual(request("POST", "/runs", start, alice)[1]["error"]["code"],
                                     "account_budget_exhausted")
                    self.assertEqual(request("POST", "/logout", {}, alice)[0], 200)
                    self.assertEqual(request("GET", "/runs", cookie=alice)[0], 401)
                    self.assertEqual(request("POST", "/login", {"username": "alice", "password": PASSWORD})[0], 200)
                finally:
                    server.shutdown()
                    thread.join()
                    service.process_lock.close()
