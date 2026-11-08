"""Ownership checks through the real HTTP routing layer, with zero inference."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import time
from scripts.application_accounts import digest
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
                    # Unauthenticated operational readiness is intentionally
                    # public, unlike owner-owned runs, exports and projects.
                    ready_status, ready, _ = request("GET", "/readiness")
                    self.assertEqual(ready_status, 200)
                    self.assertTrue(ready["can_start_complete_migration"])
                    self.assertEqual(ready["minimum_inference_requests"], 7)
                    self.assertEqual(ready["capacity_state"], "ready")
                    self.assertFalse(ready["reviewer_migration_ready"])
                    self.assertRegex(ready["capacity_resets_at"], r"^\d{4}-\d{2}-\d{2}T00:00:00Z$")
                    status, capability, _ = request("GET", "", cookie=alice)
                    self.assertEqual(status, 200)
                    self.assertEqual(capability["max_requests"], 16)
                    self.assertEqual(capability["account_daily_allowance"], 16)
                    self.assertEqual(capability["global_daily_ceiling"], 48)
                    self.assertEqual(capability["account_remaining_today"], 16)
                    self.assertEqual(capability["global_reserved_today"], 0)
                    self.assertEqual(capability["global_remaining_today"], 48)
                    # Cold reviewer URL: obtain an owner-scoped session and
                    # load the capability endpoint before any migration exists.
                    # This caught a production 502 from calling self.reserved()
                    # on the handler instead of the service.
                    review_code = "r" * 43
                    service.review_passes["review-" + digest(review_code)] = int(time.time()) + 3600
                    review_status, review_signed, review_cookie = request(
                        "POST", "/review-session", {"code": review_code})
                    self.assertEqual(review_status, 200)
                    self.assertTrue(review_signed["signed_in"])
                    self.assertEqual(request("GET", "/session", cookie=review_cookie.split(";", 1)[0])[1]["username"],
                                     "Review workspace")
                    reviewer_status, reviewer_capacity, _ = request(
                        "GET", "", cookie=review_cookie.split(";", 1)[0])
                    self.assertEqual(reviewer_status, 200)
                    self.assertEqual(reviewer_capacity["max_requests"], 15)
                    self.assertEqual(reviewer_capacity["account_daily_allowance"], 15)
                    self.assertEqual(reviewer_capacity["global_remaining_today"], 48)
                    self.assertFalse(reviewer_capacity["review_run_used"])
                    self.assertTrue(request("GET", "/readiness")[1]["reviewer_migration_ready"])
                    review_owner = service.accounts.resolve(
                        review_cookie.split(";", 1)[0].split("=", 1)[1])[0]
                    # One completed reviewer run makes migration creation
                    # unavailable, without withholding its saved evidence.
                    reviewer_run_id = "app-fedcba9876543210"
                    service.runs[reviewer_run_id] = ({
                        "id": reviewer_run_id, "mode": "application_live",
                        "owner": review_owner, "budget": 9, "model_requests": 7,
                        "started_at": now(), "status": "compatible_on_sample",
                        "export": {"model": "glm-5.2"}
                    }, [])
                    used_status, used_capability, _ = request(
                        "GET", "", cookie=review_cookie.split(";", 1)[0])
                    self.assertEqual(used_status, 200)
                    self.assertTrue(used_capability["review_run_used"])
                    self.assertEqual(used_capability["max_requests"], 0)
                    self.assertFalse(request("GET", "/readiness")[1]["reviewer_migration_ready"])
                    self.assertEqual(request("GET", f"/runs/{reviewer_run_id}",
                                             cookie=review_cookie.split(";", 1)[0])[0], 200)
                    self.assertEqual(request("GET", f"/runs/{reviewer_run_id}",
                                             cookie=bob)[0], 404)
                    service.review_passes["review-" + digest(review_code)] = int(time.time()) - 1
                    expired_status, expired, _ = request(
                        "GET", "", cookie=review_cookie.split(";", 1)[0])
                    self.assertEqual(expired_status, 200)
                    self.assertTrue(expired["review_pass_expired"])
                    self.assertEqual(expired["max_requests"], 0)
                    owner = service.accounts.resolve(alice.split("=", 1)[1])[0]
                    project = "import-1234567890abcdef"
                    service.accounts.save_project(owner, project, {"id": project},
                        {"discovery": {"preset": "llm-0.37.1"}, "source_sha256": "test", "files": {}})
                    run_id = "app-1234567890abcdef"
                    run = {"id": run_id, "status": "compatible_on_sample", "mode": "application_live",
                           "owner": owner, "budget": 16, "started_at": now(),
                           "export": {"model": "test"}}
                    service.runs[run_id] = (run, [])
                    _, limited, _ = request("GET", "", cookie=alice)
                    self.assertEqual(limited["account_remaining_today"], 0)
                    self.assertEqual(limited["global_reserved_today"], 16)
                    self.assertEqual(limited["global_remaining_today"], 32)
                    self.assertEqual(limited["max_requests"], 0)
                    # The global pool may still admit another user.
                    self.assertTrue(request("GET", "/readiness")[1]["can_start_complete_migration"])
                    # Exhaustion must not silently masquerade as availability.
                    service.runs[run_id][0]["budget"] = 44
                    degraded_status, degraded, _ = request("GET", "/readiness")
                    self.assertEqual(degraded_status, 200)
                    self.assertFalse(degraded["can_start_complete_migration"])
                    self.assertEqual(degraded["reason"], "daily_capacity_below_one_complete_migration")
                    service.runs[run_id][0]["budget"] = 16
                    service.quarantined = True
                    blocked_status, blocked, _ = request("GET", "/readiness")
                    self.assertEqual(blocked_status, 503)
                    self.assertEqual(blocked["reason"], "operator_review_required")
                    service.quarantined = False
                    _, other, _ = request("GET", "", cookie=bob)
                    self.assertEqual(other["max_requests"], 16)
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
