"""Expiring guest source must never reset the paid reservation ledger."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from scripts.application_http import ApplicationService


class GuestCleanupTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.service = ApplicationService(
            Path(self.folder.name), "guest-cleanup-private-token-over-32-characters",
            "test-image", daily_budget=128, account_budget=32,
            public_origin="https://refit.example")
        self.addCleanup(self.service.process_lock.close)
        self.accounts = self.service.accounts

    def seed(self, *, old=True):
        day = datetime.now(timezone.utc).date().isoformat()
        owner, secret = self.accounts.open_guest(day, "7" * 64)
        self.assertTrue(secret)
        ident = "import-1234567890abcdef"
        self.accounts.save_project(owner, ident, {"id": ident}, {"files": {"agent.py": "code"}})
        self.assertTrue(self.accounts.claim_guest_run(day, "7" * 64, owner, 7, "8" * 32))
        when = datetime.now(timezone.utc) - timedelta(days=3 if old else 0)
        finished = when + timedelta(minutes=5)
        run_id = "app-1111111111111111"
        run = {"id": run_id, "mode": "application_live", "status": "compatible_on_sample",
               "started_at": when.isoformat(), "finished_at": finished.isoformat(),
               "owner": owner, "budget": 7, "model_requests": 7}
        self.service.runs[run_id] = (run, [])
        self.service.store.save(run_id, run, [])
        with self.accounts.db() as db:
            db.execute("UPDATE sessions SET expires=? WHERE owner=?",
                       (int(time.time()) - 1, owner))
        return owner, run_id

    def test_cleanup_preserves_abuse_ledger_but_deletes_old_guest_source(self):
        owner, ident = self.seed()
        self.assertEqual(self.service.prune_guest_workspaces(force=True), 1)
        self.assertNotIn(ident, self.service.runs)
        self.assertFalse((self.service.store.directory / (ident + ".json")).exists())
        self.assertEqual(self.accounts.list_projects(owner), [])
        with self.accounts.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users WHERE id=?", (owner,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM guest_migrations").fetchone()[0], 1)

    def test_same_day_billing_and_recent_evidence_survive(self):
        owner, ident = self.seed(old=False)
        self.assertEqual(self.service.prune_guest_workspaces(force=True), 0)
        self.assertIn(ident, self.service.runs)
        self.assertEqual(len(self.accounts.list_projects(owner)), 1)

    def test_active_session_not_purged(self):
        day = datetime.now(timezone.utc).date().isoformat()
        owner, secret = self.accounts.open_guest(day, "9" * 64)
        self.assertTrue(secret)
        self.assertEqual(self.service.prune_guest_workspaces(force=True), 0)
        with self.accounts.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users WHERE id=?", (owner,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
