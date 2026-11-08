"""Deterministic unattended monitoring tests. No public network or model usage."""
from __future__ import annotations
import unittest
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

    def test_bounded_attempts(self):
        with self.assertRaises(ValueError):
            probe("https://example.test", attempts=0)
        with self.assertRaises(ValueError):
            probe("https://example.test", attempts=20)
        with self.assertRaises(ValueError):
            probe("https://example.test", delay=300)


if __name__ == "__main__":
    unittest.main()
