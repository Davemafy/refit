"""Anonymous live agent migration; fixed source, real endpoint, durable quotas.

These tests never call Vultr or Docker. Paid production acceptance is separate.
"""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import secrets
import time
import unittest

from scripts.application_accounts import Accounts
from scripts.application_http import (
    ApplicationService, ApplicationHandler, PUBLIC_TRIAL_ARCHIVE,
    PUBLIC_TRIAL_BUDGET, PUBLIC_TRIAL_DAILY_LIMIT, now,
)

ORIGIN = "https://refit.example"
TOKEN = "test-only-anonymous-trial-operator-secret"


class AnonymousTrialHttpTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = ApplicationService(
            Path(temporary.name), TOKEN, "reviewed-image",
            daily_budget=192, account_budget=32, public_origin=ORIGIN)
        self.addCleanup(self.service.process_lock.close)
        flags = patch.dict(os.environ, {"REFIT_PUBLIC_TRIAL_ENABLED": "1"})
        flags.start()
        self.addCleanup(flags.stop)
        handler = type("Handler", (ApplicationHandler,), {"service": self.service})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server_thread.join(timeout=3)
        self.server.server_close()

    def http(self, method, route, data=None, cookie="", ip="203.0.113.40", origin=ORIGIN):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=7)
        try:
            payload = json.dumps(data) if data is not None else None
            client.request(method, "/api/application" + route, payload,
                           {"X-Refit-Public": "1", "X-Refit-Client-IP": ip,
                            "Content-Type": "application/json", "Cookie": cookie,
                            "Origin": origin})
            response = client.getresponse()
            return response.status, json.loads(response.read()), response.getheader("Set-Cookie")
        finally:
            client.close()

    def try_run(self, ip="203.0.113.40", body=None):
        if body is None:
            body = {}
        with patch.object(self.service, "broker", return_value=SimpleNamespace(requests=0)), \
             patch.object(self.service, "launch", return_value=True):
            return self.http("POST", "/try", body, ip=ip)

    def test_no_signup_real_pinned_project_cookie_and_owner_scoped_run(self):
        self.assertEqual(self.http("GET", "/session")[1]["username"], None)
        status, response, header = self.try_run()
        self.assertEqual(status, 202, response)
        self.assertTrue(response["live"])
        self.assertTrue(response["sample"])
        self.assertRegex(response["id"], r"^app-[0-9a-f]{16}$")
        for security_flag in ("Secure", "HttpOnly", "SameSite=Strict"):
            self.assertIn(security_flag, header)
        cookie = header.split(";", 1)[0]
        session = self.http("GET", "/session", cookie=cookie)[1]
        self.assertEqual(session["username"], "Visitor")
        self.assertTrue(session["trial"])
        result = self.http("GET", "/runs/" + response["id"], cookie=cookie)
        self.assertEqual(result[0], 200, result)
        self.assertEqual(result[1]["budget"], PUBLIC_TRIAL_BUDGET)
        self.assertEqual(result[1]["source"], "deepseek-v4.1-flash-1017")
        self.assertEqual(result[1]["target"], "glm-5.2")
        project = self.http("GET", "/projects", cookie=cookie)[1]["projects"][0]
        self.assertEqual(project["repository"], "simonw/llm")
        self.assertEqual(project["discovery"]["preset"], "llm-0.37.1")
        self.assertGreater(self.http("GET", "", cookie=cookie)[1]["max_requests"], 0)
        self.assertEqual(self.http("GET", "/runs/" + response["id"])[0], 401)
        # A temporary visitor can use the full import flow. Invalid run
        # inputs are rejected by evaluation validation, not account gates.
        self.assertEqual(self.http("POST", "/runs", {"budget": 12}, cookie=cookie)[1]["error"]["code"],
                         "invalid_models")
        another = self.try_run()
        self.assertEqual(another[0], 202, another)
        self.assertNotEqual(another[1]["id"], response["id"])
        # Repeated anonymous samples share an IP ledger across cookie rotation.
        self.assertEqual(self.try_run()[0], 202)
        spent = self.try_run()
        self.assertEqual(spent[0], 429)
        self.assertEqual(spent[1]["error"]["code"], "visitor_budget_full")
        other = self.try_run(ip="203.0.113.41")
        self.assertEqual(other[0], 202, other)
        self.assertNotEqual(other[2], header)

    def test_repeat_sample_reuses_the_original_guest_workspace(self):
        self.service.account_budget = 64
        first, data, header = self.try_run(ip="203.0.113.79")
        self.assertEqual(first, 202, data)
        cookie = header.split(";", 1)[0]
        with patch.object(self.service, "broker", return_value=SimpleNamespace(requests=0)), \
             patch.object(self.service, "launch", return_value=True):
            second, response, new_cookie = self.http(
                "POST", "/try-refund", {}, cookie=cookie, ip="203.0.113.79")
        self.assertEqual(second, 202, response)
        self.assertIsNone(new_cookie, "Never replace a visitor's existing session")
        history = self.http("GET", "/runs", cookie=cookie, ip="203.0.113.79")[1]
        self.assertEqual({r["id"] for r in history["runs"]}, {data["id"], response["id"]})

    def test_public_sample_is_not_restricted_by_account_signup_allowance(self):
        # An anonymous visitor has a dedicated 32-request daily allowance
        # even when existing registered accounts are restricted to 16.
        self.service.account_budget = 16
        status, response, header = self.try_run(ip="203.0.113.78")
        self.assertEqual(status, 202, response)
        run = self.service.runs[response["id"]][0]
        self.assertEqual(run["budget"], PUBLIC_TRIAL_BUDGET)
        cookie = header.split(";", 1)[0]
        self.assertEqual(self.http("GET", "", cookie=cookie)[1]["account_daily_allowance"], 64)

    def test_origin_and_arbitrary_parameters_rejected_without_spending(self):
        self.assertEqual(self.http("POST", "/try", {}, origin="https://evil.example")[0], 403)
        self.assertEqual(self.http("POST", "/try", {"code": "print(1)"})[0], 422)
        self.assertEqual(self.http("POST", "/try", {"repository": "evil/repo"})[0], 422)
        self.assertEqual(self.try_run()[0], 202)

    def test_emergency_disable_and_fail_closed_global_capacity(self):
        with patch.dict(os.environ, {"REFIT_PUBLIC_TRIAL_ENABLED": "0"}):
            self.assertEqual(self.try_run()[1]["error"]["code"], "public_trial_disabled")
        self.service.daily_budget = 19
        self.assertEqual(self.try_run()[1]["error"]["code"], "trial_capacity_full")
        self.service.daily_budget = 192
        self.assertEqual(self.try_run()[0], 202)

    def test_fail_closed_if_vultr_credentials_are_unavailable(self):
        with patch.object(self.service, "broker", side_effect=RuntimeError("offline")):
            status, result, cookie = self.http("POST", "/try", {})
        self.assertEqual(status, 503)
        self.assertIsNone(cookie)
        self.assertEqual(result["error"]["code"], "inference_unavailable")
        self.assertEqual(self.try_run()[0], 202)

    def test_guest_daily_limit_persists_in_sqlite_and_ignores_cookies(self):
        account = self.service.accounts
        day = now()[:10]
        for i in range(PUBLIC_TRIAL_DAILY_LIMIT):
            result = account.claim_public_trial(
                day, f"{i:064x}", "guest-" + f"{i:032x}", PUBLIC_TRIAL_DAILY_LIMIT)
            self.assertEqual(result, "reserved")
        self.assertEqual(account.claim_public_trial(
            day, f"{9876:064x}", "guest-" + "d" * 32,
            PUBLIC_TRIAL_DAILY_LIMIT), "daily_limit")
        self.assertEqual(account.claim_public_trial(
            day, f"{0:064x}", "guest-" + "e" * 32,
            PUBLIC_TRIAL_DAILY_LIMIT), "already_used")
        persisted = Accounts(self.service.directory)
        self.assertEqual(persisted.claim_public_trial(
            day, f"{1234:064x}", "guest-" + "f" * 32,
            PUBLIC_TRIAL_DAILY_LIMIT), "daily_limit")


if __name__ == "__main__":
    unittest.main()
