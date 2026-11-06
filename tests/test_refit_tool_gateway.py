"""Prove the same agent-tool behavior through a separate restricted worker."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import refund_adapter, deployment_incident_probe
from scripts.sandbox_tool_gateway import (
    DOMAINS, SOURCE_FILES, ToolSandboxEnvironment,
    ToolSandboxUnavailable, sandbox_cases,
)


ROOT = Path(__file__).resolve().parent.parent


class ToolWorkerProtocolTests(unittest.TestCase):
    def simulate(self, domain: str):
        seed = 123
        case = DOMAINS[domain].make_cases(seed, "train")[0]
        local = case.environment()
        if domain == "refund":
            name = "get_order"
            args = {"order_id": local.scenario.case.order_id}
        else:
            name = "inspect_service"
            args = {"service_id": local.incident.service_id}
        expected_result = local.call(name, args)
        expected_verdict = local.verify()
        close = getattr(local, "close", None)
        if callable(close):
            close()
        request = [
            {"op": "call", "tool": name, "arguments": args},
            {"op": "verify"},
            {"op": "close"},
        ]
        cmd = [
            sys.executable, "-B", str(ROOT / "scripts" / "sandbox_tool_worker.py"),
            "--domain", domain, "--phase", "train",
            "--seed", str(seed), "--case-index", "0",
        ]
        response = subprocess.run(
            cmd, input="\n".join(json.dumps(x) for x in request) + "\n",
            text=True, capture_output=True, check=True, timeout=5,
        )
        lines = [json.loads(x) for x in response.stdout.splitlines()]
        self.assertEqual(lines[0]["result"], expected_result)
        self.assertEqual(lines[1]["verdict"], expected_verdict)
        self.assertEqual(lines[1]["events"][0]["tool"], name)
        self.assertEqual(lines[2]["closed"], True)

    def test_refund_gateway_matches_trusted_oracle(self):
        self.simulate("refund")

    def test_deployment_gateway_matches_trusted_oracle(self):
        self.simulate("deployment")

    def test_mount_allowlist_never_contains_credentials(self):
        self.assertIn("sandbox_tool_worker.py", SOURCE_FILES)
        for name in SOURCE_FILES:
            self.assertTrue(name.endswith(".py"))
            self.assertFalse(name.startswith("."))
            self.assertTrue((ROOT / "scripts" / name).is_file())
        self.assertNotIn("api_service.py", SOURCE_FILES)
        self.assertNotIn("data", SOURCE_FILES)

    def test_sandbox_case_metadata_preserves_original_agent_contract(self):
        records = []
        for domain in DOMAINS:
            orig = DOMAINS[domain].make_cases(200, "train")
            isolated = sandbox_cases(domain, 200, "train", records)
            self.assertEqual(
                [(x.name, x.request) for x in isolated],
                [(x.name, x.request) for x in orig],
            )

    def test_host_independently_verifies_sandbox_trace(self):
        # No Docker needed: the host oracle must reconstruct each authorized
        # state transition, not trust the worker-supplied success flag.
        case = DOMAINS["refund"].make_cases(123, "train")[0]
        reference = case.environment()
        try:
            reference.call("get_order", {
                "order_id": reference.scenario.case.order_id
            })
            trace = json.loads(json.dumps(reference.events))
            verdict = json.loads(json.dumps(reference.verify()))
        finally:
            reference.close()
        session = object.__new__(ToolSandboxEnvironment)
        session.domain = "refund"
        session.phase = "train"
        session.seed = 123
        session.index = 0
        session.events = []
        session._exchange = lambda command: {
            "verdict": verdict, "events": trace,
        }
        self.assertEqual(session.verify(), verdict)
        self.assertEqual(session.events, trace)

        # A worker cannot alter the business verdict even when it returns a
        # plausible-looking, valid JSON response.
        poisoned = dict(verdict, passed=not verdict["passed"])
        session._exchange = lambda command: {
            "verdict": poisoned, "events": trace,
        }
        result = session.verify()
        self.assertFalse(result["passed"])
        self.assertEqual(result["sandbox_error"], "protected_oracle_rejected_trace")

        forged_trace = json.loads(json.dumps(trace))
        forged_trace[0]["result"]["order_id"] = "FORGED"
        session._exchange = lambda command: {
            "verdict": verdict, "events": forged_trace,
        }
        result = session.verify()
        self.assertFalse(result["passed"])
        self.assertEqual(result["sandbox_error"], "protected_oracle_rejected_trace")

    @patch("scripts.sandbox_tool_gateway.shutil.which", return_value=None)
    def test_missing_docker_fails_closed(self, which):
        with self.assertRaises(ToolSandboxUnavailable):
            ToolSandboxEnvironment("refund", "train", 123, 0, [])


@unittest.skipUnless(os.getenv("REFIT_TEST_DOCKER") == "1",
                     "requires opt-in and real Docker runtime")
class LiveDockerToolTests(unittest.TestCase):
    def test_full_repair_migration_uses_only_isolated_tool_workers(self):
        # More than a Docker smoke test: the unmodified model must fail,
        # the bounded repair must pass independent validation and holdout,
        # and every stateful business tool operation must use a container.
        from scripts.sandbox_tool_gateway import migrate_in_tool_sandboxes
        from tests.test_refit_deployment import ScriptedResponder

        result = migrate_in_tool_sandboxes(
            ScriptedResponder(break_target=True),
            "deployment", "source", "target", "repair",
            seed=888, runtime="runc",
        )
        self.assertEqual(result["status"], "verified_adaptation")
        self.assertEqual(result["source_training"]["passed"], 8)
        self.assertLess(result["target_training"]["passed"], 8)
        self.assertEqual(result["validation"]["passed"], 8)
        self.assertEqual(result["repaired_holdout"]["passed"], 8)
        boundary = result["execution_boundary"]
        self.assertTrue(boundary["business_tools_isolated"])
        self.assertTrue(boundary["all_containers_removed"])
        self.assertGreater(boundary["worker_runs"], 32)
        self.assertTrue(all(x["network"] == "none" for x in boundary["cases"]))

    def test_refund_and_deployment_run_inside_restricted_containers(self):
        for domain in ("refund", "deployment"):
            with self.subTest(domain=domain):
                records = []
                local = DOMAINS[domain].make_cases(123, "train")[0].environment()
                if domain == "refund":
                    tool, args = "get_order", {
                        "order_id": local.scenario.case.order_id
                    }
                else:
                    tool, args = "inspect_service", {
                        "service_id": local.incident.service_id
                    }
                reference = local.call(tool, args)
                expected_verdict = local.verify()
                local_close = getattr(local, "close", None)
                if callable(local_close):
                    local_close()
                session = ToolSandboxEnvironment(
                    domain, "train", 123, 0, records
                )
                try:
                    self.assertEqual(session.call(tool, args), reference)
                    self.assertEqual(session.verify(), expected_verdict)
                finally:
                    session.close()
                self.assertEqual(len(records), 1)
                self.assertTrue(records[0]["container_absent"])
                self.assertEqual(records[0]["network"], "none")
                self.assertTrue(records[0]["read_only_root"])


if __name__ == "__main__":
    unittest.main()
