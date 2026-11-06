"""Release identity is a startup observation, not a moving checkout label."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts.release_identity import capture_revision
from scripts.api_service import RunService
from tests.test_refit_durability import HeldExecutor


class ReleaseIdentityTests(unittest.TestCase):
    @patch("scripts.release_identity.subprocess.run")
    def test_capture_validates_head_and_reports_tracked_changes(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
                           subprocess.CompletedProcess([], 0, " M scripts/example.py\n", "")]
        result = capture_revision(Path("/tmp/refit"))
        self.assertEqual(result["commit"], "a" * 40)
        self.assertFalse(result["tracked_files_clean"])

    @patch("scripts.release_identity.subprocess.run")
    def test_missing_git_and_timeout_leave_identity_unknown(self, run):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("git", 3)):
            run.side_effect = error
            result = capture_revision(Path("/tmp/refit"))
            self.assertIsNone(result["commit"])
            self.assertIsNone(result["tracked_files_clean"])

    @patch("scripts.api_service.capture_revision")
    def test_service_health_does_not_relabel_a_running_process_after_git_pull(self, capture):
        capture.return_value = {"commit": "a" * 40, "tracked_files_clean": True}
        service = RunService(executor=HeldExecutor())
        capture.return_value = {"commit": "b" * 40, "tracked_files_clean": True}
        self.assertEqual(service.health()["revision"]["commit"], "a" * 40)
        self.assertEqual(service.health()["revision"]["commit"], "a" * 40)
        capture.assert_called_once()

    def test_extended_operator_budget_is_explicit_and_bounded(self):
        service = RunService(executor=HeldExecutor(), max_requests=400)
        self.assertEqual(service.max_requests, 400)
        self.assertEqual(RunService(executor=HeldExecutor()).max_requests, 160)
        with self.assertRaisesRegex(ValueError, "budget"):
            RunService(max_requests=401)


if __name__ == "__main__":
    unittest.main()
