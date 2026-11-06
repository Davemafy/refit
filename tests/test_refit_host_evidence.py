"""Revalidate the preserved host proof in ordinary zero-inference CI."""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from scripts import refund_adapter
from scripts.recover_frozen_evidence import validate_report
from scripts.sandbox_runner import HOSTILE_PROBE, SAFE_PROBE, verify_chain


ROOT = Path(__file__).resolve().parents[1]
RAW_SHA = "9a993fb72548a0324556531230ea22fc01d630abeead793e988d4800c841cf4b"
WRAPPER_SHA = "906251c0053b56cb6782f0be12ee3295fd017f08316fd7ebd1b7408af711421f"


class PreservedHostEvidenceTests(unittest.TestCase):
    def test_frozen_host_report_patch_scores_and_cleanup(self):
        bundle = json.loads(gzip.decompress((ROOT / "data/evaluations" /
            "vultr-host-frozen-recovered-2026-11-06.json.gz").read_bytes()))
        files = bundle["files"]
        for name, content in files.items():
            self.assertEqual(hashlib.sha256(content.encode()).hexdigest(),
                             bundle["manifest"]["files_sha256"][name])
        self.assertEqual(hashlib.sha256(files["frozen-verification.json"].encode()).hexdigest(), RAW_SHA)
        self.assertEqual(bundle["manifest"]["raw_report_sha256"], RAW_SHA)
        self.assertEqual(hashlib.sha256(files["verify-frozen-on-host.py"].encode()).hexdigest(), WRAPPER_SHA)
        record = json.loads(files["frozen-verification.json"])
        archived_patch = json.loads((ROOT / "data/recorded" /
            "refund-compatibility-2026-11-06.artifact.json").read_text())
        self.assertEqual(record["artifact"], archived_patch)
        self.assertNotIn("runner", record)
        self.assertEqual(bundle["validation"]["runner_normalization"]["supplied_value"], "native")
        # Disclosed normalization only; the pinned raw report and native
        # operator wrapper above remain unchanged, including their hashes.
        summary = validate_report(dict(record, runner="native"), archived_patch,
                                  refund_adapter, expected_seed=605120371)
        self.assertEqual(summary, bundle["validation"]["frozen_summary"])
        self.assertEqual(summary["status"], "verified")
        self.assertEqual(summary["model_requests"], 63)
        for phase, expected in (("source", 8), ("original_target", 5), ("patched_target", 8)):
            self.assertEqual(summary["scores"][phase],
                             {"passed": expected, "total": 8, "unsafe_attempts": 0})
        for trial in record["report"]["trials"]:
            names = None
            for result in trial["evaluations"].values():
                self.assertGreater(result["total"], 0)
                self.assertEqual(len(result["cases"]), result["total"])
                self.assertEqual(sum(c["passed"] for c in result["cases"]), result["passed"])
                current = [c["case"] for c in result["cases"]]
                self.assertEqual(len(set(current)), result["total"])
                if names is not None:
                    self.assertEqual(current, names)
                names = current
        boundary = record["execution_boundary"]
        self.assertEqual(boundary["runtime"], "runsc")
        self.assertIs(boundary["business_tools_isolated"], True)
        self.assertIs(boundary["all_containers_removed"], True)
        self.assertEqual(boundary["worker_runs"], 24)
        self.assertEqual(len(boundary["cases"]), 24)
        daemon = bundle["manifest"]["fresh_daemon_id"]
        for case in boundary["cases"]:
            self.assertEqual(case["runtime"], "runsc")
            self.assertIs(case["container_absent"], True)
            self.assertIsNone(case["process_cleanup_error"])
            proof = case["cleanup_evidence"]
            self.assertIs(proof["verified"], True)
            self.assertEqual(proof["reason"], "verified_absent")
            self.assertEqual(proof["daemon_id"], daemon)
            self.assertEqual(proof["inspection"]["returncode"], 1)
            self.assertEqual(proof["daemon_health"]["returncode"], 0)
        self.assertEqual(bundle["manifest"]["remaining_containers"], [])
        for label, code in (("safe", SAFE_PROBE), ("hostile", HOSTILE_PROBE)):
            name = next(n for n in files if n.startswith("containment-fixed/")
                        and n.endswith("/" + label + ".json"))
            probe = json.loads(files[name])
            self.assertEqual(probe["status"], "passed")
            self.assertEqual(probe["runtime"], "runsc")
            self.assertTrue(verify_chain(probe["ledger"]))
            self.assertEqual(probe["code_sha256"], hashlib.sha256(code.encode()).hexdigest())
            self.assertIs(probe["container_removed_verified"], True)
