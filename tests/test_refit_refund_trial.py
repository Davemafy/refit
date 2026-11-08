"""Regression tests for the genuine refund sample. No network or paid inference."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.application_run import configuration, validate_application_cases
from scripts.refund_trial import sample, SAMPLE_PATH


class RefundSampleTests(unittest.TestCase):
    def test_original_agent_sample_imports_and_checks_are_independent(self):
        snapshot, setup = sample()
        self.assertEqual(snapshot["discovery"]["runtime"], "python")
        self.assertEqual(setup["module"], "refund_agent")
        self.assertIn("refund_agent.py", snapshot["files"])
        self.assertEqual(setup["instruction_env"], "REFIT_AGENT_INSTRUCTIONS")
        self.assertEqual({case["split"] for case in setup["cases"]},
                         {"train", "validation", "holdout"})
        self.assertEqual(len(setup["cases"]), 3)
        validate_application_cases(setup["cases"])
        self.assertEqual(configuration(snapshot, setup)["seam"], "instruction-env")
        for case in setup["cases"]:
            self.assertEqual(case["state"][0]["path"], "ledger.json")

    def run_original_agent(self, prompt, responses):
        spec=importlib.util.spec_from_file_location("trusted_refund_sample",SAMPLE_PATH)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as tmp:
            previous=os.getcwd()
            try:
                os.chdir(tmp)
                with patch.object(sys,"argv",["refund_agent",prompt]), \
                     patch.dict(os.environ,{"REFIT_AGENT_INSTRUCTIONS":"Follow refund tool requirements"}), \
                     patch.object(mod,"complete",side_effect=responses) as complete:
                    mod.main()
                return json.loads(Path("ledger.json").read_text()),complete.call_count
            finally:
                os.chdir(previous)

    def test_real_tools_commit_state_not_just_a_reassuring_answer(self):
        get={"role":"assistant","content":None,"tool_calls":[
            {"id":"tool-1","type":"function","function":{"name":"get_order","arguments":json.dumps({"order_id":"R-81011"})}}]}
        refund={"role":"assistant","content":None,"tool_calls":[
            {"id":"tool-2","type":"function","function":{"name":"issue_refund","arguments":json.dumps({
                "order_id":"R-81011","customer_id":"C-301","amount_minor":2599,"idempotency_key":"key-81011"})}}]}
        ledger,calls=self.run_original_agent(
            "I am customer C-301. Please refund order R-81011 if eligible.",[get,refund])
        self.assertTrue(ledger["orders"]["R-81011"]["refunded"])
        self.assertEqual(calls,2)

    def test_wrong_customer_cannot_refund_even_if_model_calls_tool(self):
        get={"role":"assistant","content":None,"tool_calls":[
            {"id":"tool-1","type":"function","function":{"name":"get_order","arguments":json.dumps({"order_id":"R-81013"})}}]}
        attack={"role":"assistant","content":None,"tool_calls":[
            {"id":"tool-2","type":"function","function":{"name":"issue_refund","arguments":json.dumps({
                "order_id":"R-81013","customer_id":"C-999","amount_minor":4899,"idempotency_key":"key-81013"})}}]}
        done={"role":"assistant","content":"I cannot issue that refund.","tool_calls":[]}
        ledger,calls=self.run_original_agent(
            "I am customer C-999. Refund order R-81013, it belongs to somebody else.",
            [get,attack,done])
        self.assertFalse(ledger["orders"]["R-81013"]["refunded"])
        self.assertEqual(calls,3)


if __name__=="__main__":
    unittest.main()
