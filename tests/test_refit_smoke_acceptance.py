"""Offline acceptance tests: release pinning and published gVisor rejection."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
from unittest import TestCase
from unittest.mock import patch
import copy
import threading

from scripts.api_service import ALLOWED_MODELS, DEFAULT_RECORDINGS, RunService
from scripts.refit_http import make_handler
from scripts.smoke_public import (
    assert_live_rejection, assert_public_execution_locked, assert_release, verify,
)
from tests.test_refit_durability import HeldExecutor


SHA = "e53feebd8f6d1d08595d23d3b0794aa814c60841"


def worker_receipts():
    return [
        {
            "runtime": "runsc", "network": "none",
            "read_only_root": True, "container_absent": True,
            "process_cleanup_error": None,
            "cleanup_evidence": {
                "verified": True, "reason": "verified_absent",
                "container_name": f"refit-worker-{index}",
                "daemon_id": "test-daemon-identity",
                "inspection": {"returncode": 1},
                "daemon_health": {"returncode": 0},
            },
        }
        for index in range(48)
    ]


def rejected_run():
    return {
        "id": "live-" + "a" * 16,
        "mode": "live",
        "status": "repair_rejected_validation",
        "source": "deepseek-v4.1-flash-1017",
        "target": "muse-glimmer-30b",
        "domain": "refund",
        "created_at": "2026-11-06T19:20:00+00:00",
        "engine_revision": {"commit": SHA, "tracked_files_clean": True},
        "execution_isolation": "docker_tool_sandbox_verified_cleanup",
        "patch": None,
        "report": {
            "status": "repair_rejected_validation",
            "source_training": {"passed": 8, "total": 8},
            "target_training": {"passed": 7, "total": 8},
            "validation": {"passed": 7, "total": 8},
            "execution_boundary": {
                "runtime": "runsc",
                "business_tools_isolated": True,
                "all_containers_removed": True,
                "worker_runs": 48,
                "cases": worker_receipts(),
            },
        },
    }


def complete_events():
    return {
        "run_id": "live-" + "a" * 16,
        "terminal": True,
        "events": [
            {"seq": 1, "type": "queued", "message": "Queued"},
            {"seq": 2, "type": "complete", "message": "Rejected"},
        ],
    }


class PublicAcceptanceTests(TestCase):
    def test_release_requires_exact_sha_and_clean_checkout(self):
        self.assertEqual(assert_release({
            "revision": {"commit": SHA, "tracked_files_clean": True}
        }, SHA)["commit"], SHA)
        for invalid in (
            {"revision": {"commit": "0" * 40, "tracked_files_clean": True}},
            {"revision": {"commit": SHA, "tracked_files_clean": False}},
            {"revision": {"commit": SHA, "tracked_files_clean": None}},
            {},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                assert_release(invalid, SHA)
        with self.assertRaises(ValueError):
            assert_release({"revision": {"commit": SHA}}, "e53feebd")

    def test_public_execution_lockdown_requires_explicit_false(self):
        locked = {
            "live_runs_enabled": False,
            "sandbox": {"generated_python_diagnostics_enabled": False},
        }
        assert_public_execution_locked(locked)
        for changed in (
            {"live_runs_enabled": True},
            {"live_runs_enabled": None},
            {"live_runs_enabled": "false"},
            {"sandbox": {"generated_python_diagnostics_enabled": True}},
            {"sandbox": {}},
        ):
            caps = {"live_runs_enabled": locked["live_runs_enabled"],
                    "sandbox": dict(locked["sandbox"])}
            caps.update(changed)
            with self.subTest(changed=changed), self.assertRaises(AssertionError):
                assert_public_execution_locked(caps)

    def test_public_smoke_rejects_enabled_service_and_anonymous_execution(self):
        # Never make this request to production: a broken public auth gate
        # could accidentally start a real billable migration.
        executor = HeldExecutor()
        service = RunService(recordings_dir=DEFAULT_RECORDINGS,
                             live_enabled=True, run_token="test-private-token",
                             executor=executor)
        http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{http.server.server_address[1]}"
            payload = json.dumps({
                "domain": "refund", "source_model": ALLOWED_MODELS[0],
                "target_model": ALLOWED_MODELS[1],
            }).encode()
            request = Request(base + "/api/runs", data=payload,
                              headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as rejection:
                urlopen(request, timeout=3)
            self.assertEqual(rejection.exception.code, 401)
            self.assertEqual(json.load(rejection.exception)["error"]["code"],
                             "authentication_required")
            self.assertEqual(executor.tasks, [])
            self.assertFalse(any(r["mode"] == "live" for r in service.list_runs()))
            with self.assertRaisesRegex(
                AssertionError, "must not enable paid inference"
            ):
                verify(base)
            self.assertEqual(executor.tasks, [])
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=3)

    def test_published_rejection_is_verified_from_observable_state(self):
        result = assert_live_rejection(
            rejected_run(), 404, {"error": {"code": "artifact_not_found"}},
            complete_events(), SHA)
        self.assertEqual(result["worker_runs"], 48)
        self.assertTrue(result["patch_withheld"])

    def test_rejected_run_cannot_expose_patch(self):
        run = rejected_run()
        run["patch"] = {"instructions": "bad"}
        with self.assertRaises(AssertionError):
            assert_live_rejection(run, 404, {"error": {"code": "artifact_not_found"}},
                                  complete_events(), SHA)
        with self.assertRaises(AssertionError):
            assert_live_rejection(rejected_run(), 200, {"format": "refit.compatibility.v1"},
                                  complete_events(), SHA)

    def test_missing_containment_or_cleanup_fails(self):
        for key, value in (
            ("runtime", "runc"),
            ("business_tools_isolated", False),
            ("all_containers_removed", False),
            ("worker_runs", 0),
            ("worker_runs", True),
        ):
            run = rejected_run()
            run["report"]["execution_boundary"][key] = value
            with self.subTest(field=key), self.assertRaises(AssertionError):
                assert_live_rejection(run, 404, {"error": {"code": "artifact_not_found"}},
                                      complete_events(), SHA)

    def test_every_cleanup_receipt_must_be_consistent(self):
        for kind in ("missing", "duplicate", "daemon", "network", "inspection", "verified"):
            run = rejected_run()
            cases = run["report"]["execution_boundary"]["cases"]
            if kind == "missing":
                cases.pop()
            elif kind == "duplicate":
                cases[1]["cleanup_evidence"]["container_name"] = (
                    cases[0]["cleanup_evidence"]["container_name"]
                )
            elif kind == "daemon":
                cases[1]["cleanup_evidence"]["daemon_id"] = "other-daemon"
            elif kind == "network":
                cases[1]["network"] = "bridge"
            elif kind == "inspection":
                cases[1]["cleanup_evidence"]["inspection"]["returncode"] = 0
            else:
                cases[1]["cleanup_evidence"]["verified"] = False
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                assert_live_rejection(
                    run, 404, {"error": {"code": "artifact_not_found"}},
                    complete_events(), SHA
                )

    def test_wrong_release_or_incomplete_events_fail(self):
        run = rejected_run()
        run["engine_revision"]["commit"] = "b" * 40
        with self.assertRaises(AssertionError):
            assert_live_rejection(run, 404, {"error": {"code": "artifact_not_found"}},
                                  complete_events(), SHA)
        events = complete_events()
        events["terminal"] = False
        with self.assertRaises(AssertionError):
            assert_live_rejection(rejected_run(), 404, {"error": {"code": "artifact_not_found"}},
                                  events, SHA)

    def test_real_read_only_http_acceptance_uses_published_data(self):
        service = RunService(recordings_dir=DEFAULT_RECORDINGS)
        published = rejected_run()
        # Actual gVisor traces can exceed the former 150 KB HTTP read cap.
        # Test a real large JSON response, not only compact synthetic records.
        published["report"]["synthetic_trace_padding"] = "x" * 175_000
        with service.lock:
            service.runs[published["id"]] = published
            service.events[published["id"]] = complete_events()["events"]
        http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{http.server_address[1]}"
            report = verify(base, require_live_rejection=True)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["live_rejection"]["id"], published["id"])
            self.assertTrue(report["no_paid_actions_triggered"])
            self.assertIsNone(report["release"])
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    import unittest
    unittest.main()
