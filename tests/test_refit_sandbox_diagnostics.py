"""Offline tests for host-verified, Vultr-generated sandbox diagnostics."""
import json
from pathlib import Path
import unittest

from scripts.sandbox_diagnostics import (
    diagnostics_input, expected_diagnostic, extract_python, generate_and_verify,
)


ROOT = Path(__file__).resolve().parent.parent


class FakeClient:
    def __init__(self):
        self.calls = []
    def complete(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        return {"content": "print('model wrote this program')"}


class FakeSandbox:
    def __init__(self, alter=False, cleanup=True):
        self.alter = alter
        self.cleanup = cleanup
        self.calls = []
    def run(self, code, inputs, label):
        self.calls.append((code, inputs, label))
        result = expected_diagnostic(inputs)
        if self.alter:
            result["training_regression_delta"] = 999
        return {
            "status": "passed", "ledger_valid": True,
            "container_removed_verified": self.cleanup,
            "stdout": json.dumps(result),
        }


class DiagnosticTests(unittest.TestCase):
    def record(self, name):
        path = ROOT / "data" / "recorded" / f"{name}-2026-11-06.json"
        return json.loads(path.read_text(encoding="utf8"))

    def test_expected_refund_from_actual_recorded_run(self):
        record = self.record("refund")
        expected = expected_diagnostic(diagnostics_input(record))
        self.assertEqual(expected, {
            "training_regression_delta": 2,
            "target_failed_cases": ["ineligible", "timeout_after_commit"],
            "holdout_improvement": 1,
        })

    def test_compatible_deployment_does_not_invent_regression(self):
        expected = expected_diagnostic(diagnostics_input(self.record("deployment")))
        self.assertEqual(expected["training_regression_delta"], 0)
        self.assertEqual(expected["target_failed_cases"], [])
        self.assertIsNone(expected["holdout_improvement"])

    def test_model_program_is_issued_and_checked_against_host_oracle(self):
        client, sandbox = FakeClient(), FakeSandbox()
        result = generate_and_verify(
            self.record("refund"), client, "deepseek-v4.1-flash-1017", sandbox)
        self.assertTrue(result["verified"])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][2]["max_tokens"], 1600)
        self.assertEqual(len(sandbox.calls), 1)
        self.assertEqual(sandbox.calls[0][2], "model_generated_diagnostic")
        self.assertEqual(result["observed"], result["expected"])

    def test_rejects_wrong_generated_answer_and_missing_cleanup(self):
        for sandbox in (FakeSandbox(alter=True), FakeSandbox(cleanup=False)):
            with self.subTest(sandbox=sandbox):
                result = generate_and_verify(
                    self.record("refund"), FakeClient(),
                    "deepseek-v4.1-flash-1017", sandbox)
                self.assertFalse(result["verified"])

    def test_script_extractor_strips_fences_not_prose(self):
        fence = chr(96) * 3
        self.assertEqual(
            extract_python({"content": fence + "python\nprint(1)\n" + fence}),
            "print(1)",
        )
        self.assertEqual(extract_python({"content": "print(2)"}), "print(2)")
        with self.assertRaises(ValueError):
            extract_python({"content": ""})
        with self.assertRaises(ValueError):
            extract_python({"content": "a" * 21000})

    def test_no_report_or_invalid_domain_does_not_trigger_model(self):
        with self.assertRaises(ValueError):
            diagnostics_input({"domain": "unknown", "report": {}})
        with self.assertRaises(ValueError):
            diagnostics_input({"domain": "refund", "report": {}})
        with self.assertRaises(ValueError):
            diagnostics_input({
                "domain": "refund", "report": {
                    "source_training": {"passed": True, "total": 8},
                    "target_training": {"passed": 6, "total": 8}
                }
            })


if __name__ == "__main__":
    unittest.main()
