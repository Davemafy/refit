"""No-charge acceptance gating tests. Never calls Vultr or executes Docker."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class PaidTypeScriptAcceptanceGateTests(unittest.TestCase):
    def invoke(self, enabled, ceiling):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.json"
            output = root / "receipt.json"
            request.write_text(json.dumps({
                "run_live": enabled, "source": "deepseek-v4.1-flash-1017",
                "target": "glm-5.2", "max_requests": ceiling
            }))
            env = os.environ.copy()
            env.pop("VULTR_INFERENCE_API_KEY", None)
            proc = subprocess.run(
                [sys.executable, "-m", "scripts.acceptance_typescript_live",
                 "--archive", str(root / "nonexistent.zip"),
                 "--setup", str(root / "nonexistent.json"),
                 "--request", str(request), "--output", str(output)],
                capture_output=True, text=True, env=env, timeout=15
            )
            self.assertFalse(output.exists(), "Gate must not fabricate a live receipt")
            return proc

    def test_disabled_or_missing_key_never_spends(self):
        self.assertEqual(self.invoke(False, 48).returncode, 0)
        missing = self.invoke(True, 48)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Missing VULTR_INFERENCE_API_KEY", missing.stderr)

    def test_over_budget_is_rejected_before_any_source_load(self):
        blocked = self.invoke(True, 49)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("at most 48 requests", blocked.stderr)


if __name__ == "__main__":
    unittest.main()
