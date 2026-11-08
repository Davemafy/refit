"""Account-bound, single-use generated diagnostics for real migration records."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.api_service import ApiProblem
from scripts.application_http import ApplicationService, public_challenge_one, now
from scripts.sandbox_diagnostics import diagnostics_input, expected_diagnostic
from scripts.sandbox_runner import DockerSandbox, SandboxUnavailable


REPORT = {
    "source_training": {"passed": 2, "total": 2, "failed": []},
    "target_training": {"passed": 1, "total": 2, "failed": ["case_one"]},
    "original_holdout": {"passed": 0, "total": 1, "failed": ["private-case"]},
    "repaired_holdout": {"passed": 1, "total": 1, "failed": []},
    "source_failure_evidence": [{"prompt": "secret original user input"}],
}
RUN_ID = "app-aaaaaaaaaaaaaaaa"
TOKEN = "test-diagnostic-operator-token-32-long"
ORIGIN = "https://refit.example"


def evidence(cleanup=True, runtime="runsc", status="passed", verified=True):
    expected = expected_diagnostic(diagnostics_input({"domain": "application", "report": REPORT}))
    return {
        "kind": "vultr_model_generated_python_diagnostic",
        "generator_model": "deepseek-v4.1-flash-1017",
        "generated_code": "print('code returned by model')",
        "expected": expected, "observed": expected,
        "verified": verified, "validation_error": None,
        "cross_check": {"sandbox": {
            "status": status, "runtime": runtime, "container_created": True,
            "container_removed_verified": cleanup, "ledger_valid": True}},
        "sandbox": {
            "status": status, "runtime": runtime, "container_created": True,
            "exit_code": 0 if status == "passed" else 1,
            "stdout": json.dumps(expected), "stderr": "",
            "container_removed_verified": cleanup, "ledger_valid": True,
            "cleanup_evidence": {"verified": cleanup},
        },
    }


class DiagnosticAccountTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.service = ApplicationService(self.root, TOKEN, "refit-image",
                                          daily_budget=5, account_budget=4,
                                          public_origin=ORIGIN)
        self.addCleanup(self.service.process_lock.close)
        session = self.service.accounts.register("diagowner", "test password 123")
        self.owner = self.service.accounts.resolve(session)[0]
        run = {"id": RUN_ID, "mode": "application_live", "status": "candidate_failed_validation",
               "owner": self.owner, "started_at": now(), "finished_at": now(),
               "source": "deepseek-v4.1-flash-1017", "target": "glm-5.2",
               "budget": 2, "model_requests": 2, "report": REPORT, "export": None}
        self.service.runs[RUN_ID] = (run, [])
        self.service.store.save(RUN_ID, run, [])
        self.env = patch.dict(os.environ, {
            "REFIT_ENABLE_SANDBOX_DIAGNOSTICS": "1",
            "REFIT_SANDBOX_RUNTIME": "runsc",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def start(self):
        with patch.object(ApplicationService, "broker",
                          return_value=SimpleNamespace(requests=0, max_requests=1)), \
             patch("scripts.application_http.threading.Thread.start", return_value=None):
            return self.service.diagnose(RUN_ID, self.owner)

    def test_generation_input_is_only_measured_training_not_holdout(self):
        inputs = diagnostics_input({"domain": "application", "report": REPORT})
        self.assertEqual(set(inputs["phases"]), {"source_training", "target_training"})
        self.assertNotIn("private-case", json.dumps(inputs))
        self.assertNotIn("secret original", json.dumps(inputs))
        self.assertEqual(expected_diagnostic(inputs)["holdout_improvement"], None)

    def test_single_use_run_owned_budgeted_and_persisted(self):
        self.assertEqual(self.service.reserved(now()[:10], self.owner), 2)
        result = self.start()
        self.assertEqual(result["status"], "running")
        self.assertEqual(self.service.reserved(now()[:10], self.owner), 3)
        self.assertEqual(self.service.get(RUN_ID, self.owner)[1][-1]["type"], "diagnostic_requested")
        with self.assertRaises(ApiProblem) as dup:
            self.start()
        self.assertEqual(dup.exception.code, "diagnostic_already_requested")
        with self.assertRaises(ApiProblem) as no_access:
            self.service.get(RUN_ID, "another-owner")
        self.assertEqual(no_access.exception.code, "run_not_found")
        broker = SimpleNamespace(requests=1)
        with patch("scripts.application_http.DockerSandbox") as docker, \
             patch("scripts.application_http.generate_and_verify", return_value=evidence()) as generated:
            self.service._execute_diagnostic(RUN_ID, {"domain": "application", "report": REPORT}, broker)
        docker.assert_called_once_with(
            runtime="runsc", staging_root=Path("/var/lib/refit-application/sandbox-staging"))
        self.assertEqual(generated.call_args.args[2], "deepseek-v4.1-flash-1017")
        completed, events = self.service.get(RUN_ID, self.owner)
        self.assertEqual(completed["diagnostic"]["status"], "verified")
        self.assertTrue(completed["diagnostic"]["verified"])
        self.assertEqual(completed["diagnostic"]["model_requests"], 1)
        self.assertEqual(events[-1]["type"], "diagnostic_finished")
        self.assertIsNone(completed["export"])
        self.assertTrue((self.root / "runs" / (RUN_ID + ".json")).exists())

    def test_unverified_cleanup_quarantines_execution(self):
        self.start()
        with patch("scripts.application_http.DockerSandbox"), \
             patch("scripts.application_http.generate_and_verify", return_value=evidence(cleanup=False)):
            self.service._execute_diagnostic(RUN_ID, {"domain": "application", "report": REPORT},
                                             SimpleNamespace(requests=1))
        self.assertTrue(self.service.quarantined)
        self.assertFalse(self.service.get(RUN_ID, self.owner)[0]["diagnostic"]["verified"])

    def test_unverified_runtime_and_execution_failure_do_not_pass(self):
        for record in (evidence(runtime="runc"), evidence(status="execution_failed")):
            with self.subTest(record=record["sandbox"]["status"]):
                self.service.runs[RUN_ID][0].pop("diagnostic", None)
                self.start()
                with patch("scripts.application_http.DockerSandbox"), \
                     patch("scripts.application_http.generate_and_verify", return_value=record):
                    self.service._execute_diagnostic(
                        RUN_ID, {"domain": "application", "report": REPORT},
                        SimpleNamespace(requests=1))
                self.assertEqual(self.service.get(RUN_ID, self.owner)[0]["diagnostic"]["status"], "rejected")

    def test_feature_gate_and_budget_exhaustion(self):
        with patch.dict(os.environ, {"REFIT_ENABLE_SANDBOX_DIAGNOSTICS": "0"}):
            with self.assertRaises(ApiProblem) as disabled:
                self.start()
            self.assertEqual(disabled.exception.code, "diagnostic_disabled")
        self.service.account_budget = 2
        with self.assertRaises(ApiProblem) as exhausted:
            self.start()
        self.assertEqual(exhausted.exception.code, "account_budget_exhausted")
        self.assertNotIn("diagnostic", self.service.get(RUN_ID, self.owner)[0])

    def test_incomplete_migration_and_review_owner_rejected(self):
        self.service.runs[RUN_ID][0]["status"] = "running"
        with self.assertRaises(ApiProblem) as active:
            self.start()
        self.assertEqual(active.exception.code, "run_not_finished")
        self.service.runs[RUN_ID][0]["status"] = "failed"
        self.service.runs[RUN_ID][0]["report"] = {}
        with self.assertRaises(ApiProblem) as incomplete:
            self.start()
        self.assertEqual(incomplete.exception.code, "insufficient_migration_evidence")

    def test_interrupted_diagnostic_is_not_retried_on_restart(self):
        self.start()
        self.service.process_lock.close()
        restored = ApplicationService(self.root, TOKEN, "refit-image",
                                      public_origin=ORIGIN)
        self.addCleanup(restored.process_lock.close)
        diag = restored.get(RUN_ID, self.owner)[0]["diagnostic"]
        self.assertEqual(diag["status"], "interrupted")
        self.assertEqual(diag["error"], "service_restarted_no_automatic_retry")


class PublicChallengeProofTests(unittest.TestCase):
    def test_recorded_production_evidence_matches_observed_outputs(self):
        record = public_challenge_one()
        self.assertTrue(record["recorded"])
        self.assertTrue(record["public_sample"])
        run = record["run"]
        self.assertEqual(run["model_requests"], 7)
        diagnostic = run["diagnostic"]
        self.assertEqual(diagnostic["status"], "verified")
        self.assertEqual(diagnostic["model_requests"], 1)
        for item in (diagnostic["sandbox"], diagnostic["cross_check"]["sandbox"]):
            self.assertEqual(item["runtime"], "runsc")
            self.assertTrue(item["container_removed_verified"])
            self.assertEqual(item["exit_code"], 0)
        self.assertEqual(json.loads(diagnostic["sandbox"]["stdout"]), diagnostic["expected"])
        self.assertEqual(json.loads(diagnostic["cross_check"]["sandbox"]["stdout"]), diagnostic["cross_check"]["expected"])


class GvisorIdentityTests(unittest.TestCase):
    @patch("scripts.sandbox_runner.subprocess.run")
    def test_accepts_registered_runsc_binary(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, '{"runsc":{"path":"/usr/bin/runsc"}}', ""),
            subprocess.CompletedProcess([], 0, "runsc version release-2026\n", ""),
        ]
        receipt = DockerSandbox(runtime="runsc")._runtime_identity({"PATH": "/usr/bin"})
        self.assertEqual(receipt["docker_runtime"], "runsc")
        self.assertIn("runsc version", receipt["version"])

    @patch("scripts.sandbox_runner.subprocess.run")
    def test_rejects_runtime_alias_pointing_at_runc(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, '{"runsc":{"path":"/usr/bin/runc"}}', "")
        with self.assertRaises(SandboxUnavailable):
            DockerSandbox(runtime="runsc")._runtime_identity({"PATH": "/usr/bin"})
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
