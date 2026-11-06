"""The exact failure modes that otherwise make live agent demos unreliable."""
from __future__ import annotations

from concurrent.futures import Future
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.api_service import ALLOWED_MODELS, ApiProblem, RunService
from scripts.durable_store import RunStore


class HeldExecutor:
    def __init__(self):
        self.tasks = []

    def submit(self, fn, *args):
        self.tasks.append((fn, args))
        return Future()


class FakeInference:
    def __init__(self, *_args, **_kwargs):
        self.requests = 3


class DurabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "runs"
        self.executor = HeldExecutor()
        self.payload = {
            "domain": "refund",
            "source_model": ALLOWED_MODELS[0],
            "target_model": ALLOWED_MODELS[1],
        }

    def make_service(self, **kwargs):
        return RunService(
            runs_dir=self.directory, live_enabled=True, run_token="private",
            executor=kwargs.pop("executor", HeldExecutor()), **kwargs
        )

    def test_real_migration_engine_reports_truthful_stages(self):
        from scripts.deployment_incident_probe import run_live
        from tests.test_refit_deployment import ScriptedResponder

        progress = []
        result = run_live(
            ScriptedResponder(break_target=True),
            "source", "target", "repair", seed=888,
            progress=lambda kind, details: progress.append((kind, details)),
        )
        self.assertEqual(result["status"], "verified_adaptation")
        phases = [
            details for kind, details in progress if kind == "phase_completed"
        ]
        self.assertEqual(phases[0]["phase"], "source_training")
        self.assertEqual(phases[0]["passed"], 8)
        self.assertEqual(phases[1]["phase"], "target_training")
        self.assertLess(phases[1]["passed"], 8)
        self.assertTrue(any(k == "repair_started" for k, _ in progress))
        self.assertTrue(any(k == "repair_generated" for k, _ in progress))
        self.assertTrue(any(p["phase"] == "validation" for p in phases))
        self.assertEqual(phases[-1]["phase"], "repaired_holdout")
        self.assertEqual(phases[-1]["passed"], 8)
        for phase in phases:
            self.assertLessEqual(phase["passed"], phase["total"])
            self.assertEqual(phase["total"], 8)
            self.assertGreaterEqual(phase["unsafe_attempts"], 0)

    def test_api_http_reconnects_after_restart_with_original_event_cursor(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import urlopen
        from scripts.refit_http import make_handler

        first = self.make_service(executor=self.executor)
        run_id = first.start(self.payload, "private")["id"]

        def serve_once(service, path):
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}{path}"
                with urlopen(url, timeout=3) as response:
                    return json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)

        first_events = serve_once(first, f"/api/runs/{run_id}/events?after=0")
        self.assertEqual(first_events["next_after"], 1)
        self.assertFalse(first_events["terminal"])
        recovered = self.make_service()
        second_events = serve_once(recovered, f"/api/runs/{run_id}/events?after=1")
        self.assertTrue(second_events["terminal"])
        self.assertEqual([e["type"] for e in second_events["events"]], ["interrupted"])
        self.assertEqual(second_events["next_after"], 2)
        final_record = serve_once(recovered, f"/api/runs/{run_id}")
        self.assertEqual(final_record["status"], "execution_interrupted")
        self.assertIsNone(final_record["patch"])

    def test_live_history_is_ordered_by_creation_not_random_file_id(self):
        older = "live-" + "f" * 16
        newer = "live-" + "a" * 16
        for id_, created in (
            (older, "2026-11-05T11:00:00Z"),
            (newer, "2026-11-06T11:00:00Z"),
        ):
            run = {
                "id": id_, "mode": "live", "domain": "refund",
                "source": ALLOWED_MODELS[0], "target": ALLOWED_MODELS[1],
                "status": "compatible_on_sample", "created_at": created,
                "patch": None, "report": {},
            }
            RunStore(self.directory).save(
                id_, run, [{"seq": 1, "type": "complete", "message": "Completed."}]
            )
        svc = self.make_service()
        ids = [x["id"] for x in svc.list_runs()]
        self.assertEqual(ids[:2], [newer, older])

    def test_queue_is_on_disk_before_worker_is_scheduled(self):
        service = self.make_service(executor=self.executor)
        result = service.start(self.payload, "private")
        run_id = result["id"]
        self.assertEqual(result["status"], "queued")
        stored = json.loads((self.directory / (run_id + ".json")).read_text())
        self.assertEqual(stored["schema"], 2)
        self.assertEqual(stored["run"]["status"], "queued")
        self.assertEqual(stored["events"][0]["type"], "queued")
        self.assertEqual(stored["events"][0]["seq"], 1)
        self.assertEqual(len(self.executor.tasks), 1)
        self.assertEqual(self.executor.tasks[0][0].__name__, "_execute")
        self.assertEqual(
            (self.directory / (run_id + ".json")).stat().st_mode & 0o777,
            0o600,
        )

    def test_restart_recovers_run_without_replaying_paid_actions(self):
        first = self.make_service(executor=self.executor, daily_limit=1)
        run_id = first.start(self.payload, "private")["id"]
        self.assertEqual(len(self.executor.tasks), 1)
        # Simulate process restart. A separate RunService MUST NOT submit the
        # old queued job again or expose it as a completed migration.
        second_executor = HeldExecutor()
        second = self.make_service(executor=second_executor, daily_limit=1)
        restored = second.get_run(run_id)
        self.assertEqual(restored["status"], "execution_interrupted")
        self.assertIsNone(restored["patch"])
        self.assertEqual(restored["error"]["code"], "worker_interrupted")
        stream = second.get_events(run_id)
        self.assertTrue(stream["terminal"])
        self.assertEqual([e["type"] for e in stream["events"]],
                         ["queued", "interrupted"])
        self.assertEqual(second.get_events(run_id, after=2)["events"], [])
        self.assertEqual(len(second_executor.tasks), 0)
        with self.assertRaises(ApiProblem) as error:
            second.start(self.payload, "private")
        self.assertEqual(error.exception.status, 429)
        # Recovery is idempotent; a third boot does not append another event.
        third = self.make_service(daily_limit=1)
        self.assertEqual(third.get_run(run_id)["status"], "execution_interrupted")
        self.assertEqual(third.get_events(run_id)["next_after"], 2)

    def test_recorded_success_and_measured_events_survive_restart(self):
        first = self.make_service(executor=self.executor)
        run_id = first.start(self.payload, "private")["id"]

        def deterministic_run(_client, _source, _target, _repair, seed, progress):
            self.assertIsInstance(seed, int)
            progress("phase_started", {
                "phase": "source_training", "model": ALLOWED_MODELS[0],
            })
            progress("phase_completed", {
                "phase": "source_training", "model": ALLOWED_MODELS[0],
                "passed": 8, "total": 8, "unsafe_attempts": 0,
            })
            progress("phase_started", {
                "phase": "target_training", "model": ALLOWED_MODELS[1],
            })
            progress("phase_completed", {
                "phase": "target_training", "model": ALLOWED_MODELS[1],
                "passed": 8, "total": 8, "unsafe_attempts": 0,
            })
            return {
                "status": "compatible_on_sample",
                "source_training": {"passed": 8, "total": 8},
                "target_training": {"passed": 8, "total": 8},
                "validation": {"passed": 8, "total": 8},
                "original_holdout": {"passed": 8, "total": 8},
            }

        with (
            patch("scripts.api_service.load_key", return_value="fake"),
            patch("scripts.api_service.VultrInference", FakeInference),
            patch("scripts.refund_adapter.run_live", side_effect=deterministic_run),
        ):
            fn, args = self.executor.tasks.pop()
            fn(*args)
        completed = first.get_run(run_id)
        self.assertEqual(completed["status"], "compatible_on_sample")
        self.assertEqual(completed["model_requests"], 3)
        self.assertIn("evaluation_seed", completed)
        self.assertEqual(first.get_events(run_id)["events"][-1]["type"], "complete")
        second = self.make_service()
        self.assertEqual(second.get_run(run_id)["status"], "compatible_on_sample")
        self.assertEqual(second.get_run(run_id)["report"]["target_training"]["passed"], 8)
        events = second.get_events(run_id)["events"]
        self.assertEqual([e["type"] for e in events], [
            "queued", "started", "phase_started", "phase_completed",
            "phase_started", "phase_completed", "complete",
        ])
        self.assertEqual(events[3]["details"]["passed"], 8)
        self.assertEqual(events[3]["details"]["total"], 8)
        self.assertEqual(events[3]["details"]["unsafe_attempts"], 0)

    def test_persistence_failure_prevents_any_inference(self):
        service = self.make_service(executor=self.executor)
        with patch.object(RunStore, "save", side_effect=OSError("disk full")):
            with self.assertRaises(ApiProblem) as raised:
                service.start(self.payload, "private")
        self.assertEqual(raised.exception.code, "persistence_unavailable")
        self.assertIsNone(service.active)
        self.assertEqual(service.started_dates, [])
        self.assertEqual(len(self.executor.tasks), 0)
        self.assertEqual(len(service.list_runs()), 2)

    def test_legacy_and_corrupt_files_are_handled_conservatively(self):
        directory = self.directory
        directory.mkdir(parents=True)
        old_id = "live-" + "a" * 16
        old = {
            "id": old_id, "mode": "live", "domain": "refund",
            "source": ALLOWED_MODELS[0], "target": ALLOWED_MODELS[1],
            "status": "compatible_on_sample", "created_at": "2026-10-21T10:00:00Z",
            "patch": None, "report": {"target_training": {"passed": 8, "total": 8}},
        }
        (directory / (old_id + ".json")).write_text(json.dumps(old))
        (directory / ("live-" + "b" * 16 + ".json")).write_text("{broken")
        svc = self.make_service()
        self.assertEqual(svc.get_run(old_id)["status"], "compatible_on_sample")
        self.assertEqual(svc.get_events(old_id)["events"][0]["type"], "restored")
        self.assertEqual(svc.capabilities()["recovery_warnings"], 1)
        self.assertEqual(len(svc.list_runs()), 3)

    def test_event_validator_rejects_untrusted_progress_shapes(self):
        svc = self.make_service(executor=self.executor)
        run_id = svc.start(self.payload, "private")["id"]
        with self.assertRaises(ValueError):
            svc._progress(run_id, "phase_completed", {
                "phase": "target_training", "passed": True,
                "total": 8, "unsafe_attempts": 0,
            })
        with self.assertRaises(ValueError):
            svc._progress(run_id, "faker_success", {"passed": 8})


if __name__ == "__main__":
    unittest.main()
