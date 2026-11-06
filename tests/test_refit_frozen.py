"""Frozen verification never requests a new repair or hides failed trials."""
import unittest
from unittest.mock import patch
import contextlib
import io
import json
from pathlib import Path
import tempfile

from scripts import deployment_incident_probe as incident
from scripts.compatibility_artifact import create_receipt
from scripts.migration_engine import AgentProfile
from scripts.verify_frozen_patch import verify_frozen, main
from tests.test_refit_deployment import ScriptedResponder


class FrozenPatchTests(unittest.TestCase):
    def test_fixed_patch_repeats_without_requesting_repair(self):
        class NoOptimizer(ScriptedResponder):
            def complete(self, model, messages, tools=None):
                if tools is None:
                    raise AssertionError("Frozen evaluation cannot optimize")
                return super().complete(model, messages, tools)

        result = verify_frozen(
            NoOptimizer(break_target=True), incident,
            AgentProfile(incident.INSTRUCTIONS + " Remediation: complete inspections."),
            "source", "target", [2301, 2302, 2303], paraphrase=True)
        self.assertEqual(result["status"], "frozen_patch_passed_sample")
        self.assertEqual(result["summary"]["patched_target"]["passed"], 24)
        self.assertEqual(len(result["trials"]), 3)
        self.assertEqual(result["summary"]["original_target"]["passed"], 0)

    def test_failed_patch_keeps_all_predeclared_trials(self):
        result = verify_frozen(ScriptedResponder(break_target=True), incident,
                               incident.BASE_PROFILE, "source", "target", [10, 11])
        self.assertEqual(result["status"], "frozen_patch_failed_verification")
        self.assertEqual(len(result["trials"]), 2)

    def test_rejects_empty_or_duplicate_seeds(self):
        for seeds in ([], [4, 4]):
            with self.assertRaises(ValueError):
                verify_frozen(ScriptedResponder(), incident, incident.BASE_PROFILE,
                              "source", "target", seeds)

    def test_budget_exhaustion_is_not_reported_as_agent_regression(self):
        class Exhausted:
            def complete(self, *args, **kwargs):
                raise RuntimeError("live inference request budget exhausted")
        result = verify_frozen(Exhausted(), incident, incident.BASE_PROFILE,
                               "source", "target", [10, 11])
        self.assertEqual(result["status"], "inference_budget_exhausted")
        self.assertEqual(len(result["trials"]), 1)
        self.assertIn("source", result["trials"][0]["evaluations"])

    def test_command_preview_does_not_load_key_or_call_models(self):
        report = incident.run_live(ScriptedResponder(break_target=True),
                                   "source", "target", "repair", 888)
        receipt = create_receipt(report, incident.CONTRACT, incident.BASE_PROFILE,
                                  "source", "target")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "patch.json"
            path.write_text(json.dumps(receipt))
            with patch("sys.argv", ["verify_frozen_patch", "--patch", str(path),
                                    "--seeds", "1", "2"]), patch(
                    "scripts.verify_frozen_patch.load_key",
                    side_effect=AssertionError("Preview must not load credentials")):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    main()
            self.assertFalse(json.loads(output.getvalue())["execute"])


if __name__ == "__main__":
    unittest.main()
