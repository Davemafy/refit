"""No-inference tests for the guarded Vultr operator release path."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import operator_live as op
from scripts.api_service import ALLOWED_MODELS, RunService
from tests.test_refit_durability import HeldExecutor, FakeInference


class OperatorTests(unittest.TestCase):
    def test_dry_run_never_contacts_provider_or_vm(self):
        command = [
            "operator_live", "--domain", "refund",
            "--source", ALLOWED_MODELS[0],
            "--target", ALLOWED_MODELS[1],
        ]
        capture = io.StringIO()
        with (
            patch("sys.argv", command),
            patch.object(op, "check_runtime") as runtime,
            patch.object(op, "run_operator") as execute,
            redirect_stdout(capture),
        ):
            op.main()
        self.assertEqual(json.loads(capture.getvalue())["mode"], "dry_run_only")
        runtime.assert_not_called()
        execute.assert_not_called()

    def test_publish_rejects_active_job_and_writes_owned_atomic_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / ("live-" + "a" * 16 + ".json")
            target = root / "public"
            payload = {
                "schema": 2,
                "run": {"id": old.stem, "mode": "live", "status": "running"},
                "events": [
                    {"seq": 1, "type": "queued", "message": "queued"},
                    {"seq": 2, "type": "started", "message": "started"},
                ],
            }
            old.write_text(json.dumps(payload))
            with self.assertRaises(RuntimeError):
                op.publish_record(old, target, os.getuid(), os.getgid())
            self.assertFalse(target.exists())
            payload["run"]["status"] = "compatible_on_sample"
            old.write_text(json.dumps(payload))
            published = op.publish_record(old, target, os.getuid(), os.getgid())
            self.assertEqual(published.name, old.name)
            self.assertEqual(published.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(published.read_text())["run"]["status"],
                             "compatible_on_sample")
            self.assertEqual(list(target.glob("*.tmp")), [])

    def test_missing_registered_gvisor_refuses_to_run(self):
        with (
            patch.object(op.os, "geteuid", return_value=0),
            patch("scripts.operator_live.KEY_PATH") as key,
            patch.object(op.os, "access", return_value=True),
            patch.object(op.shutil, "which", return_value="/bin/mock"),
            patch.object(op.subprocess, "run") as command,
        ):
            key.is_file.return_value = True
            command.return_value.stdout = '{"runc": {}}'
            with self.assertRaisesRegex(RuntimeError, "not registered"):
                op.check_runtime()
            self.assertEqual(command.call_count, 1)

    def test_rejects_unsafe_runtime_result_before_issuing_compatibility_patch(self):
        from scripts.api_service import RunService
        with tempfile.TemporaryDirectory() as temp:
            tasks = HeldExecutor()
            service = RunService(
                runs_dir=Path(temp), executor=tasks,
                live_enabled=True, run_token="operator",
            )
            run_id = service.start({
                "domain": "refund",
                "source_model": ALLOWED_MODELS[0],
                "target_model": ALLOWED_MODELS[1],
            }, "operator")["id"]
            with (
                patch.dict(os.environ, {
                    "REFIT_USE_TOOL_SANDBOX": "1",
                    "REFIT_SANDBOX_RUNTIME": "runsc",
                    "REFIT_ENABLE_SANDBOX_DIAGNOSTICS": "0",
                }),
                patch("scripts.api_service.load_key", return_value="fake"),
                patch("scripts.api_service.VultrInference", FakeInference),
                patch("scripts.sandbox_tool_gateway.migrate_in_tool_sandboxes",
                      return_value={
                          "status": "verified_adaptation",
                          "execution_boundary": {
                              "runtime": "runsc",
                              "business_tools_isolated": True,
                              "all_containers_removed": False,
                              "worker_runs": 8,
                          },
                      }),
                patch("scripts.api_service.create_receipt") as create,
            ):
                fn, args = tasks.tasks.pop()
                fn(*args)
                create.assert_not_called()
            recorded = service.get_run(run_id)
            self.assertEqual(recorded["status"], "execution_error")
            self.assertIsNone(recorded["patch"])
            self.assertTrue(service.get_events(run_id)["terminal"])


if __name__ == "__main__":
    unittest.main()
