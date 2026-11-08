"""Independent fail-closed tests for redacted Vultr host containment receipts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.api_service import ApiProblem
from scripts.c1_public_receipt import sanitize
from scripts.application_http import public_containment_proof

SHA = "c" * 40

def observed_worker(timeout=False):
    return {
        "status": "timeout" if timeout else "passed",
        "runtime": "runsc",
        "runtime_identity": {"docker_runtime": "runsc",
                             "version": "runsc version release-20261102.0\nspec: 1.2.1"},
        "container_created": True, "container_removed_verified": True,
        "ledger_valid": True, "timed_out": timeout,
        "exit_code": 137 if timeout else 0,
        "stdout": "" if timeout else json.dumps({
            "host_canary_read": "FileNotFoundError",
            "outbound_network": "OSError", "root_write": "PermissionError",
            "host_key_env_present": False,
        }),
        "unsafe_host_field": "/etc/refit/inference.env",
        "container_id": "private-daemon-id",
    }

def raw_acceptance():
    return {
        "verified": True, "host_canary_unchanged": True,
        "prohibited_actions_observed": True, "timeout_enforced": True,
        "forbidden": observed_worker(), "timeout": observed_worker(timeout=True),
    }

class PublicReceiptTests(unittest.TestCase):
    def test_verified_observations_are_redacted_and_bound_to_revision(self):
        safe = sanitize(raw_acceptance(), SHA)
        self.assertEqual(safe["revision"], SHA)
        self.assertTrue(safe["verified"])
        self.assertFalse(safe["generated_by_model"])
        self.assertEqual(len(safe["attempts"]), 5)
        self.assertTrue(all(action["blocked"] for action in safe["attempts"]))
        self.assertTrue(all(worker["cleanup_verified"] for worker in safe["workers"]))
        content = json.dumps(safe)
        for fragment in ("/etc/refit", "private-daemon-id", "unsafe_host_field",
                         "VULTR_INFERENCE_API_KEY", "container_id"):
            self.assertNotIn(fragment, content)

    def test_rejects_unverified_host_change_egress_timeout_and_cleanup(self):
        for field in ("verified", "host_canary_unchanged",
                      "prohibited_actions_observed", "timeout_enforced"):
            item = raw_acceptance()
            item[field] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                sanitize(item, SHA)
        for name, field, value in [
            ("forbidden", "container_removed_verified", False),
            ("timeout", "ledger_valid", False),
            ("forbidden", "stdout", json.dumps({
                "host_canary_read": "FileNotFoundError",
                "outbound_network": "unexpectedly_connected",
                "root_write": "PermissionError", "host_key_env_present": False,
            })),
        ]:
            item = raw_acceptance()
            item[name][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                sanitize(item, SHA)

    def test_public_endpoint_refuses_stale_or_missing_proof(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "public.json"
            path.write_text(json.dumps(sanitize(raw_acceptance(), SHA)))
            with patch("scripts.application_http.PUBLIC_CONTAINMENT_RECEIPT", path):
                self.assertTrue(public_containment_proof(SHA)["verified"])
                with self.assertRaises(ApiProblem) as error:
                    public_containment_proof("d" * 40)
                self.assertEqual(error.exception.code, "containment_proof_unavailable")
                path.unlink()
                with self.assertRaises(ApiProblem):
                    public_containment_proof(SHA)

if __name__ == "__main__":
    unittest.main()
