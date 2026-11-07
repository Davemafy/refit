"""Exercise durable scheduling and authorization without sending model requests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scripts.api_service import ApiProblem
from scripts.application_http import ApplicationService

ORIGIN = "https://refit.example"
SNAPSHOT = {"files": {}, "source_sha256": "pinned-source"}
REQUEST = {"source": "deepseek-v4.1-flash-1017", "target": "glm-5.2",
           "budget": 2, "authorize": True}
PRIVATE_SETUP = {"holdout": "private test expectation"}
START_THREAD = Thread.start


class ApplicationQueueTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name)
        config = patch("scripts.application_http.configuration", return_value=PRIVATE_SETUP)
        broker = patch.object(ApplicationService, "broker", side_effect=lambda _: SimpleNamespace(requests=0))
        executor = patch("scripts.application_http.threading.Thread.start")
        for dependency in (config, broker, executor):
            dependency.start()
            self.addCleanup(dependency.stop)

    def service(self, **kwargs):
        service = ApplicationService(self.state, "test-operator-token-32-characters", "image",
                                     public_origin=ORIGIN, **kwargs)
        self.addCleanup(service.process_lock.close)
        return service

    def project(self, service, username):
        secret = service.accounts.register(username, "test-only password")
        owner = service.accounts.resolve(secret)[0]
        summary = service.save_import(SNAPSHOT, owner, 0)
        return owner, {**REQUEST, "import_id": summary["id"]}

    def test_one_worker_per_owner_cancellation_and_atomic_reservations(self):
        service = self.service(daily_budget=6, max_active=2)
        alice, alice_request = self.project(service, "alice")
        bob, bob_request = self.project(service, "bob")
        active = service.start(alice_request, alice)
        queued = service.start(alice_request, alice)
        other = service.start(bob_request, bob)
        self.assertEqual((active["status"], queued["status"], other["status"]),
                         ("running", "queued", "running"))
        self.assertNotIn("_queued_setup", queued)
        with self.assertRaises(ApiProblem) as blocked:
            service.start(bob_request, bob)
        self.assertEqual(blocked.exception.code, "daily_budget_exhausted")
        for action in (service.get, service.cancel):
            with self.assertRaises(ApiProblem) as forbidden:
                action(queued["id"], bob)
            self.assertEqual(forbidden.exception.code, "run_not_found")
        with self.assertRaises(ApiProblem) as blocked:
            service.remove_project(alice, alice_request["import_id"])
        self.assertEqual(blocked.exception.code, "project_queued")
        self.assertEqual(service.cancel(queued["id"], alice)["status"], "cancelled")
        self.assertEqual(service.start(bob_request, bob)["status"], "queued")
        self.assertEqual(service.get(queued["id"], alice)[1][-1]["details"]["model_requests"], 0)

    def test_restart_dispatches_queued_jobs_without_retrying_active_jobs(self):
        service = self.service()
        alice, alice_request = self.project(service, "alice")
        bob, bob_request = self.project(service, "bob")
        active = service.start(alice_request, alice)
        queued = service.start(bob_request, bob)
        self.assertEqual(queued["status"], "queued")
        service.process_lock.close()

        recovered = self.service()
        self.assertEqual(recovered.get(active["id"], alice)[0]["status"], "interrupted")
        run, events = recovered.get(queued["id"], bob)
        self.assertEqual(run["status"], "running")
        self.assertEqual([event["type"] for event in events], ["run_queued", "run_started"])
        self.assertNotIn("_queued_setup", run)
        self.assertNotIn("_queued_setup", (self.state / "runs" / (run["id"] + ".json")).read_text())

    def test_legacy_run_without_owner_does_not_break_project_removal(self):
        service = self.service()
        alice, request = self.project(service, "alice")
        bob, _ = self.project(service, "bob")
        service.runs["app-1234567890abcdef"] = ({"status": "interrupted"}, [])
        self.assertFalse(service.remove_project(bob, request["import_id"]))
        self.assertTrue(service.remove_project(alice, request["import_id"]))

    def test_simultaneous_submissions_cannot_oversubscribe(self):
        service = self.service(daily_budget=2, max_active=2)
        projects = [self.project(service, name) for name in ("alice", "bob")]
        barrier = Barrier(2)
        outcomes = []

        def submit(owner, request):
            barrier.wait(timeout=5)
            try:
                outcomes.append(service.start(request, owner)["status"])
            except ApiProblem as exc:
                outcomes.append(exc.code)

        # Let the caller threads run while keeping the migration worker inert.
        with patch("scripts.application_http.threading.Thread.start",
                   new=lambda thread: START_THREAD(thread) if thread.name.startswith("submission-") else None):
            threads = [Thread(target=submit, args=project, name=f"submission-{i}")
                       for i, project in enumerate(projects)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=6)
        self.assertCountEqual(outcomes, ["running", "daily_budget_exhausted"])
