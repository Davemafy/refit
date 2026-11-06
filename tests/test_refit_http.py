"""Backend contract tests; no paid inference, network egress, or secrets."""
from concurrent.futures import Future
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.api_service import (
    ALLOWED_MODELS, DEFAULT_RECORDINGS, ApiProblem, RunService, interpret,
)
from scripts.refit_http import make_handler


class DeferredExecutor:
    def __init__(self):
        self.tasks = []
    def submit(self, fn, *args):
        self.tasks.append((fn, args))
        return Future()


class ServiceTests(unittest.TestCase):
    def service(self, **kwargs):
        return RunService(recordings_dir=DEFAULT_RECORDINGS, **kwargs)

    def test_recorded_runs_came_from_genuine_reports(self):
        service = self.service()
        summaries = {r["id"]: r for r in service.list_runs()}
        self.assertEqual(set(summaries), {
            "recorded-refund-2026-11-06",
            "recorded-deployment-2026-11-06",
        })
        refund = service.get_run("recorded-refund-2026-11-06")
        self.assertEqual(refund["status"], "verified_adaptation")
        self.assertEqual(refund["report"]["target_training"]["passed"], 6)
        self.assertEqual(refund["report"]["repaired_holdout"]["passed"], 8)
        self.assertIn("42207396750", refund["evidence_url"])
        deployment = service.get_run("recorded-deployment-2026-11-06")
        self.assertEqual(deployment["status"], "compatible_on_sample")
        self.assertIsNone(deployment["patch"])

    def test_capabilities_do_not_claim_external_import_or_sandbox(self):
        capabilities = self.service().capabilities()
        self.assertFalse(capabilities["external_agent_import"])
        self.assertFalse(capabilities["sandbox"]["integrated"])
        self.assertFalse(capabilities["live_runs_enabled"])

    def test_natural_language_interpretation_is_explicitly_constrained(self):
        result = interpret("Move our refund agent from DeepSeek to Muse")
        self.assertEqual(result["domain"], "refund")
        self.assertEqual(result["source_model"], "deepseek-v4.1-flash-1017")
        self.assertEqual(result["target_model"], "muse-glimmer-30b")
        self.assertEqual(result["missing"], [])
        self.assertTrue(result["requires_confirmation"])
        result = interpret("Please migrate my agent to Muse")
        self.assertIsNone(result["domain"])
        self.assertIsNone(result["source_model"])
        self.assertEqual(result["target_model"], "muse-glimmer-30b")
        self.assertFalse(result["ready_for_review"])

    def test_live_disabled_by_default(self):
        service = self.service()
        with self.assertRaises(ApiProblem) as cm:
            service.start({"domain": "refund",
                           "source_model": ALLOWED_MODELS[0],
                           "target_model": ALLOWED_MODELS[1]}, "")
        self.assertEqual(cm.exception.status, 503)

    def test_operator_token_required_before_any_live_run(self):
        service = self.service(live_enabled=True, run_token="token", executor=DeferredExecutor())
        payload = {"domain": "refund",
                   "source_model": ALLOWED_MODELS[0],
                   "target_model": ALLOWED_MODELS[1]}
        with self.assertRaises(ApiProblem) as cm:
            service.start(payload, "wrong")
        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(len(service.list_runs()), 2)

    def test_never_execute_user_supplied_adapter_code_or_model(self):
        service = self.service(live_enabled=True, run_token="token", executor=DeferredExecutor())
        payload = {"domain": "refund", "source_model": ALLOWED_MODELS[0],
                   "target_model": ALLOWED_MODELS[1],
                   "adapter_code": "import os"}
        with self.assertRaises(ApiProblem) as cm:
            service.start(payload, "token")
        self.assertEqual(cm.exception.code, "invalid_request")
        payload.pop("adapter_code")
        payload["target_model"] = "custom-unapproved-model"
        with self.assertRaises(ApiProblem) as cm:
            service.start(payload, "token")
        self.assertEqual(cm.exception.code, "unsupported_config")

    def test_daily_quota_single_concurrency_and_event_cursor(self):
        executor = DeferredExecutor()
        service = self.service(live_enabled=True, run_token="token", daily_limit=1,
                               executor=executor)
        payload = {"domain": "refund",
                   "source_model": ALLOWED_MODELS[0], "target_model": ALLOWED_MODELS[1]}
        started = service.start(payload, "token")
        self.assertEqual(started["status"], "queued")
        self.assertEqual(len(executor.tasks), 1)
        with self.assertRaises(ApiProblem) as cm:
            service.start(payload, "token")
        self.assertEqual(cm.exception.status, 409)
        events = service.get_events(started["id"])
        self.assertEqual(events["events"][0]["type"], "queued")
        self.assertFalse(events["terminal"])
        self.assertEqual(service.get_events(started["id"], after=1)["events"], [])
        # Force a terminal state without contacting any inference endpoint.
        with service.lock:
            service.active = None
            service.runs[started["id"]]["status"] = "execution_error"
        with self.assertRaises(ApiProblem) as cm:
            service.start(payload, "token")
        self.assertEqual(cm.exception.status, 429)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = RunService(recordings_dir=DEFAULT_RECORDINGS)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.service))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, body=None, auth=None):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth:
            headers["Authorization"] = "Bearer " + auth
        req = Request(self.base + path, data=data, headers=headers)
        try:
            with urlopen(req, timeout=4) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def test_frontend_can_load_capabilities_and_recorded_runs(self):
        code, caps = self.request("/api/capabilities")
        self.assertEqual(code, 200)
        self.assertIn("refund", caps["domains"])
        code, data = self.request("/api/runs")
        self.assertEqual(code, 200)
        self.assertEqual(len(data["runs"]), 2)
        id_ = data["runs"][0]["id"]
        code, detail = self.request("/api/runs/" + id_)
        self.assertEqual(code, 200)
        self.assertIn("report", detail)
        code, events = self.request("/api/runs/" + id_ + "/events")
        self.assertEqual(code, 200)
        self.assertTrue(events["terminal"])

    def test_http_natural_language_migration_proposal(self):
        status, data = self.request("/api/interpret",
                                    {"text": "move deployment from DeepSeek to Raon"})
        self.assertEqual(status, 200)
        self.assertEqual(data["domain"], "deployment")
        self.assertTrue(data["ready_for_review"])
        self.assertTrue(data["requires_confirmation"])

    def test_live_call_never_runs_without_explicit_gate(self):
        status, data = self.request("/api/runs", {
            "domain": "refund", "source_model": ALLOWED_MODELS[0],
            "target_model": ALLOWED_MODELS[1],
        })
        self.assertEqual(status, 503)
        self.assertEqual(data["error"]["code"], "live_disabled")

    def test_bad_paths_and_malformed_json_are_consistent(self):
        status, data = self.request("/api/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "not_found")
        status, data = self.request("/api/runs/no-such-run")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "run_not_found")
        status, data = self.request("/api/runs/recorded-refund-2026-11-06/events?after=oops")
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "invalid_cursor")
        status, data = self.request("/api/interpret", {"hello": "wrong"})
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
