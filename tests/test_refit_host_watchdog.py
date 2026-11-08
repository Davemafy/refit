"""Host watchdog policy checks: no worker interruption and no quota bypass."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from scripts import host_watchdog as guard


class HostWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        root = Path(self.folder.name)
        self.root = root
        self.patches = [
            patch.object(guard, "LOCK", root / "deploy.lock"),
            patch.object(guard, "COUNTER", root / "watchdog" / "misses"),
            patch.object(guard, "PROMOTED", root / "release"),
            patch("scripts.host_watchdog.os.geteuid", return_value=0),
        ]
        for p in self.patches:
            p.start()
        (root / "release").write_text("a" * 40 + "\n")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.folder.cleanup()

    def test_healthy_requires_no_restart(self):
        with patch.object(guard, "valid_release", return_value=True), \
             patch.object(guard, "active_workers") as active, \
             patch.object(guard.subprocess, "run") as proc:
            self.assertEqual(guard.repair()["status"], "healthy")
            self.assertEqual(guard.missed_count(), 0)
            active.assert_not_called()
            proc.assert_not_called()

    def test_never_interrupts_running_containers(self):
        with patch.object(guard, "valid_release", return_value=False), \
             patch.object(guard, "active_workers", return_value=True), \
             patch.object(guard.subprocess, "run") as proc:
            self.assertEqual(guard.repair()["status"], "unhealthy_observing")
            self.assertEqual(guard.repair()["status"], "unhealthy_observing")
            outcome = guard.repair()
            self.assertEqual(outcome["status"], "active_worker_preserved")
            self.assertFalse(outcome["changed"])
            proc.assert_not_called()

    def test_restart_only_after_three_failures_and_no_worker(self):
        observed = iter([False, False, False, True])
        with patch.object(guard, "valid_release", side_effect=lambda _: next(observed)), \
             patch.object(guard, "active_workers", return_value=False), \
             patch.object(guard.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0)) as process:
            guard.repair()
            guard.repair()
            self.assertEqual(process.call_count, 0)
            self.assertEqual(guard.repair()["status"], "recovered")
            self.assertEqual(guard.missed_count(), 0)
            process.assert_called_once()
            self.assertEqual(process.call_args.args[0],
                             ["/usr/bin/systemctl", "restart", "refit-application.service"])

    def test_fails_closed_when_worker_enumeration_fails(self):
        guard.record_missed(2)
        with patch.object(guard, "valid_release", return_value=False), \
             patch.object(guard, "active_workers",
                          side_effect=subprocess.TimeoutExpired("docker", 7)), \
             patch.object(guard.subprocess, "run") as process:
            self.assertEqual(guard.repair()["status"], "worker_state_unknown")
            process.assert_not_called()

    def test_during_deploy_no_checks_or_restarts(self):
        import fcntl
        with guard.LOCK.open("a") as active_lock:
            fcntl.flock(active_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(guard, "valid_release") as health, \
                 patch.object(guard.subprocess, "run") as process:
                self.assertEqual(guard.repair()["status"], "deployment_in_progress")
                health.assert_not_called()
                process.assert_not_called()

    def test_list_only_exact_refit_worker_names(self):
        fake = SimpleNamespace(returncode=0, stdout=(
            "refit-worker-unrelated\nrefit-app-0123456789abcdefabcd\nmy-postgres\n"))
        with patch.object(guard.subprocess, "run", return_value=fake):
            self.assertTrue(guard.active_workers())
        fake.stdout = "refit-app-incorrect\nsystem-db\n"
        with patch.object(guard.subprocess, "run", return_value=fake):
            self.assertFalse(guard.active_workers())


if __name__ == "__main__":
    unittest.main()
