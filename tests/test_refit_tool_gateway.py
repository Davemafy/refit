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

    @patch("scripts.sandbox_tool_gateway.shutil.which", return_value=None)
    def test_missing_docker_fails_closed(self, which):
        with self.assertRaises(ToolSandboxUnavailable):
            ToolSandboxEnvironment("refund", "train", 123, 0, [])


@unittest.skipUnless(os.getenv("REFIT_TEST_DOCKER") == "1",
                     "requires opt-in and real Docker runtime")
class LiveDockerToolTests(unittest.TestCase):
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
