"""Visitor access for real source imports: no signup or password, never shared across clients."""
import base64
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from scripts.application_accounts import Accounts
from scripts.application_http import (
    ApplicationHandler, ApplicationService, PUBLIC_TRIAL_ARCHIVE, now,
)

ORIGIN = "https://refit.example"
TOKEN = "visitor-test-operator-token-long-enough-32"


class NoAccountImportTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.service = ApplicationService(
            Path(folder.name), TOKEN, "sandbox-image",
            daily_budget=192, account_budget=32, public_origin=ORIGIN)
        self.addCleanup(self.service.process_lock.close)
        handler = type("Handler", (ApplicationHandler,), {"service": self.service})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server = server
        self.thread = Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()

    def http(self, method, route, body=None, cookie="", ip="198.51.100.8", origin=ORIGIN):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=12)
        try:
            headers = {"Origin": origin, "X-Refit-Public": "1",
                       "X-Refit-Client-IP": ip, "Content-Type": "application/json",
                       "Cookie": cookie}
            client.request(method, "/api/application" + route,
                           json.dumps(body) if body is not None else None, headers)
            response = client.getresponse()
            return response.status, json.loads(response.read()), response.getheader("Set-Cookie")
        finally:
            client.close()

    def open_guest(self, ip="198.51.100.8"):
        status, body, header = self.http("POST", "/guest-session", {}, ip=ip)
        self.assertEqual(status, 201, body)
        self.assertTrue(body["guest"])
        self.assertEqual(body["username"], "Visitor")
        self.assertTrue(all(flag in header for flag in ("Secure", "HttpOnly", "SameSite=Strict")))
        return header.split(";", 1)[0]

    def import_sample_zip(self, cookie, ip="198.51.100.8"):
        # A real source archive, not a fabricated project ID.
        data = {"method": "zip", "archive": base64.b64encode(PUBLIC_TRIAL_ARCHIVE.read_bytes()).decode("ascii")}
        status, body, _ = self.http("POST", "/imports", data, cookie=cookie, ip=ip)
        self.assertEqual(status, 201, body)
        self.assertEqual(body["discovery"]["preset"], "llm-0.37.1")
        return body["id"]

    def start_without_inference(self, cookie, project, ip="198.51.100.8", budget=20):
        with patch.object(self.service, "broker", return_value=SimpleNamespace(requests=0)), \
             patch.object(self.service, "launch", return_value=True):
            return self.http("POST", "/runs", {
                "import_id": project, "source": "deepseek-v4.1-flash-1017",
                "target": "glm-5.2", "budget": budget, "authorize": True,
            }, cookie=cookie, ip=ip)

    def test_no_account_import_and_run_have_own_private_session(self):
        self.assertIsNone(self.http("GET", "/session")[1]["username"])
        cookie = self.open_guest()
        session = self.http("GET", "/session", cookie=cookie)[1]
        self.assertEqual(session["username"], "Visitor")
        self.assertTrue(session["trial"])
        same = self.http("POST", "/guest-session", {}, cookie=cookie)
        self.assertEqual(same[0], 200)
        self.assertIsNone(same[2], "Idempotent requests do not rotate guest identity")
        project = self.import_sample_zip(cookie)
        self.assertEqual(len(self.http("GET", "/projects", cookie=cookie)[1]["projects"]), 1)
        created = self.start_without_inference(cookie, project)
        self.assertEqual(created[0], 202, created)
        self.assertRegex(created[1]["id"], r"^app-[0-9a-f]{16}$")
        self.assertEqual(created[1]["budget"], 20)
        self.assertEqual(self.http("GET", "/runs/" + created[1]["id"], cookie=cookie)[0], 200)
        self.assertEqual(self.http("GET", "/runs/" + created[1]["id"])[0], 401)
        cookie_two = self.open_guest("198.51.100.9")
        self.assertEqual(self.http("GET", "/projects", cookie=cookie_two, ip="198.51.100.9")[1]["projects"], [])
        self.assertEqual(self.http("GET", "/runs/" + created[1]["id"], cookie=cookie_two, ip="198.51.100.9")[0], 404)
        self.assertEqual(self.http("GET", "", cookie=cookie)[1]["account_remaining_today"], 12)

    def test_branded_domain_is_an_explicit_approved_guest_origin(self):
        with patch.dict("os.environ", {"REFIT_PUBLIC_ORIGIN_ALIASES": "https://refit.davemafy.xyz"}):
            with TemporaryDirectory() as folder:
                approved = ApplicationService(
                    Path(folder), TOKEN, "sandbox-image",
                    daily_budget=64, account_budget=32, public_origin=ORIGIN)
                self.assertEqual(
                    approved.allowed_origins,
                    {ORIGIN, "https://refit.davemafy.xyz"})
                approved.process_lock.close()
        self.service.allowed_origins.add("https://refit.davemafy.xyz")
        status, result, cookie = self.http(
            "POST", "/guest-session", {}, origin="https://refit.davemafy.xyz")
        self.assertEqual(status, 201, result)
        self.assertTrue(result["guest"])
        self.assertIn("HttpOnly", cookie)

    def test_guest_budget_cannot_reset_by_clearing_cookie(self):
        accounts = self.service.accounts
        day = now()[:10]
        client = "a" * 64
        self.assertTrue(accounts.claim_guest_run(day, client, "guest-one", 32, "1" * 32))
        self.assertTrue(accounts.claim_guest_run(day, client, "guest-two", 32, "2" * 32))
        self.assertFalse(accounts.claim_guest_run(day, client, "guest-three", 1, "3" * 32))
        persisted = Accounts(self.service.directory)
        self.assertFalse(persisted.claim_guest_run(day, client, "guest-four", 1, "4" * 32))
        accounts.release_guest_run("2" * 32, "guest-two")
        self.assertTrue(persisted.claim_guest_run(day, client, "guest-four", 20, "4" * 32))

    def test_invalid_run_releases_claim_and_origin_is_checked(self):
        self.assertEqual(self.http("POST", "/guest-session", {}, origin="https://other.invalid")[0], 403)
        self.assertEqual(self.http("POST", "/guest-session", {"admin": True})[0], 422)
        cookie = self.open_guest()
        invalid = self.start_without_inference(cookie, "import-does-not-exist")
        self.assertEqual(invalid[0], 404)
        # Invalid run must not lock out a valid run.
        project = self.import_sample_zip(cookie)
        good = self.start_without_inference(cookie, project)
        self.assertEqual(good[0], 202, good)
        over = self.start_without_inference(cookie, project, budget=33)
        self.assertEqual(over[0], 422)

    def test_session_issuance_is_bounded_but_multiple_users_are_isolated(self):
        cookies = [self.open_guest() for _ in range(12)]
        self.assertEqual(len(set(cookies)), 12)
        status, body, header = self.http("POST", "/guest-session", {})
        self.assertEqual(status, 429)
        self.assertEqual(body["error"]["code"], "guest_session_rate_limited")
        self.assertIsNone(header)
        self.assertEqual(self.http("GET", "/projects", cookie=cookies[0])[1]["projects"], [])


if __name__ == "__main__":
    unittest.main()
