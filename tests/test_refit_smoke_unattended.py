"""Deterministic unattended monitoring tests. No public network or model usage."""
from __future__ import annotations
import unittest
import io
import json
from unittest.mock import patch
from scripts.smoke_unattended import inspect
from scripts.smoke_unattended import probe


class ProductionMonitorTests(unittest.TestCase):
    def test_recover_after_transient_failure(self):
        attempts = iter([
            {"ok": False, "reason": "daily_capacity_below_one_complete_migration"},
            {"ok": True, "reason": None, "revision": "a" * 40},
        ])
        delays = []
        result = probe("https://example.test", attempts=3, delay=1,
                       check=lambda _: next(attempts), sleeper=delays.append)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(delays, [1])

    def test_persistent_quarantine_is_never_reported_healthy(self):
        result = probe("https://example.test", attempts=3, delay=0,
                       check=lambda _: {"ok": False, "reason": "operator_review_required"},
                       sleeper=lambda _: None)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["observations"], ["operator_review_required"] * 3)

    def test_transport_failure_does_not_leak_details(self):
        result = probe("https://example.test", attempts=2, delay=0,
                       check=lambda _: (_ for _ in ()).throw(OSError("SECRET_TOKEN=xyz")),
                       sleeper=lambda _: None)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["reason"], "OSError")
        self.assertNotIn("SECRET_TOKEN", str(result))

    def test_real_inspector_accepts_review_only_mode_but_reports_public_depletion(self):
        class Response(io.BytesIO):
            status = 200

        origin = "https://refit.example"
        base = {"online": True, "revision": "a" * 40,
                "minimum_inference_requests": 7,
                "can_start_complete_migration": False,
                "capacity_state": "unavailable",
                "reason": "daily_capacity_below_one_complete_migration",
                "reviewer_migration_ready": True,
                "capacity_resets_at": "2026-11-09T00:00:00Z"}
        with patch("scripts.smoke_unattended.https_check",
                   return_value={"deployed_revision": "a" * 40}), patch(
                   "scripts.smoke_unattended.urlopen",
                   side_effect=lambda *args, **kwargs: Response(json.dumps(base).encode())):
            result = inspect(origin)
            self.assertTrue(result["ok"])
            self.assertEqual(result["readiness_mode"], "review_only")
            self.assertFalse(result["public_migration_ready"])
            self.assertTrue(result["reviewer_migration_ready"])
        base["reviewer_migration_ready"] = False
        with patch("scripts.smoke_unattended.https_check",
                   return_value={"deployed_revision": "a" * 40}), patch(
                   "scripts.smoke_unattended.urlopen",
                   side_effect=lambda *args, **kwargs: Response(json.dumps(base).encode())):
            result = inspect(origin)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "daily_capacity_below_one_complete_migration")

    def test_bounded_attempts(self):
        with self.assertRaises(ValueError):
            probe("https://example.test", attempts=0)
        with self.assertRaises(ValueError):
            probe("https://example.test", attempts=20)
        with self.assertRaises(ValueError):
            probe("https://example.test", delay=300)


if __name__ == "__main__":
    unittest.main()
