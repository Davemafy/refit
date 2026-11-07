"""Independent outcome evaluation never executes imported application code."""
import unittest

from scripts.application_oracle import evaluate, validate_case


class ApplicationOracleTests(unittest.TestCase):
    def sample(self, **kwargs):
        return {"name": "case_1", "split": "train", "prompt": "Answer", **kwargs}

    def test_legacy_stdout(self):
        case = self.sample(stdout="  HELLO ")
        validate_case(case)
        self.assertTrue(evaluate(case, "HELLO\n", [], False)["passed"])
        self.assertFalse(evaluate(case, "different", [], False)["passed"])

    def test_json_subset_with_nested_fields(self):
        case = self.sample(json_contains={"order": {"status": "paid", "quantity": 2}, "ok": True})
        validate_case(case)
        result = evaluate(case, '{"order":{"status":"paid","quantity":2,"id":"o1"},"ok":true,"debug":1}', [], False)
        self.assertTrue(result["passed"])
        self.assertFalse(evaluate(case, '{"order":{"status":"refunded","quantity":2},"ok":true}', [], False)["passed"])
        self.assertFalse(evaluate(case, "not json", [], False)["passed"])

    def test_tool_calls_and_forbidden_actions(self):
        case = self.sample(tool="get_order", tool_result="shipped", forbidden_tools=["delete_order"])
        validate_case(case)
        self.assertTrue(evaluate(case, "", ["get_order"], True)["passed"])
        self.assertFalse(evaluate(case, "", ["get_order", "delete_order"], True)["passed"])
        self.assertFalse(evaluate(case, "", ["get_order"], False)["passed"])
        self.assertFalse(evaluate(case, "", [], False)["passed"])

    def test_rejects_missing_and_contradictory_checks(self):
        for case in (self.sample(), self.sample(tool_result="ok", stdout="ok"),
                     self.sample(tool="get_order", forbidden_tools=["get_order"]),
                     self.sample(json_contains={}),
                     self.sample(json_contains={"bad": float("nan")})):
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_case(case)

    def test_configuration_accepts_non_stdout_checks_without_a_preset(self):
        import base64
        from scripts.application_run import configuration
        case = self.sample(json_contains={"ok": True}, tool="get_order")
        cases = [{**case, "name": split, "split": split, "prompt": split}
                 for split in ("train", "validation", "holdout")]
        snapshot = {"discovery": {"runtime": "python", "preset": None, "setup": None},
                    "files": {"agent.py": base64.b64encode(b"print(1)").decode()}}
        result = configuration(snapshot, {"module": "agent", "args": ["{prompt}"], "cases": cases})
        self.assertEqual(result["seam"], "openai-env")
        self.assertNotIn("stdout", result["cases"][0])

    def test_original_instruction_environment_and_native_export(self):
        import base64
        from scripts.application_run import configuration, native_export
        from integrations.application.worker import instruction_environment
        case = self.sample(stdout="OK")
        cases = [{**case, "name": split, "split": split, "prompt": split}
                 for split in ("train", "validation", "holdout")]
        snapshot = {"discovery": {"runtime": "python", "preset": None, "setup": None},
                    "files": {"agent.py": base64.b64encode(b"print(1)").decode()},
                    "source_sha256": "a" * 64, "repository": None, "revision": None}
        supplied = {"module": "agent", "args": ["{prompt}"], "cases": cases,
                    "instruction_env": "SYSTEM_PROMPT", "instruction_base": "Keep original tool rules."}
        setup = configuration(snapshot, supplied)
        self.assertEqual(setup["seam"], "instruction-env")
        self.assertEqual(instruction_environment({**setup, "instructions": ""}),
                         {"SYSTEM_PROMPT": "Keep original tool rules."})
        patch = "Be concise while preserving all tool rules."
        exported = native_export(snapshot, setup, "glm-5.2", patch)
        self.assertEqual(instruction_environment(exported)["SYSTEM_PROMPT"],
                         "Keep original tool rules.\n\n" + patch)
        self.assertEqual(exported["environment"]["SYSTEM_PROMPT"],
                         "Keep original tool rules.\n\n" + patch)

    def test_instruction_seam_cannot_override_system_runtime_variables(self):
        import base64
        from scripts.application_run import configuration
        from integrations.application.worker import instruction_environment
        snapshot = {"discovery": {"runtime": "python", "preset": None, "setup": None},
                    "files": {"agent.py": base64.b64encode(b"print(1)").decode()}}
        cases = [{**self.sample(stdout="OK"), "name": split, "split": split, "prompt": split}
                 for split in ("train", "validation", "holdout")]
        for key in ("OPENAI_API_KEY", "PYTHONPATH", "AGENT_RESET_DB", "NODE_OPTIONS"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration(snapshot, {"module": "agent", "args": ["{prompt}"], "cases": cases,
                                         "instruction_env": key, "instruction_base": "Policy"})
            with self.assertRaises(ValueError):
                instruction_environment({"seam": "instruction-env", "instruction_env": key,
                                         "instruction_base": "Policy", "instructions": "More"})
        with self.assertRaises(ValueError):
            configuration(snapshot, {"module": "agent", "args": ["{prompt}"], "cases": cases,
                                     "instruction_env": "SYSTEM_PROMPT"})

    def test_boolean_is_not_number(self):
        case = self.sample(json_contains={"count": 1})
        self.assertFalse(evaluate(case, '{"count":true}', [], False)["passed"])


if __name__ == "__main__":
    unittest.main()
