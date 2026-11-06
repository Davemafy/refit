"""Read-only frozen host report recovery requires complete, bound evidence."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.compatibility_artifact import digest, validate_and_load
from scripts import refund_adapter
from scripts.recover_frozen_evidence import (
    DEFAULT_PATCH, candidates, read_report, validate_report,
)


def fixture():
    receipt = json.loads(DEFAULT_PATCH.read_text(encoding="utf8"))
    profile = validate_and_load(receipt, refund_adapter.CONTRACT,
                                refund_adapter.BASE_PROFILE, receipt["target_model"])
    profile_sha = digest({"instructions": profile.instructions,
                          "tool_descriptions": dict(profile.tool_descriptions)})
    outcomes = {
        "source": {"passed": 8, "total": 8, "unsafe_attempts": 0,
                   "model_requests": 18},
        "original_target": {"passed": 7, "total": 8, "unsafe_attempts": 0,
                            "model_requests": 19},
        "patched_target": {"passed": 8, "total": 8, "unsafe_attempts": 0,
                           "model_requests": 20},
    }
    report = {
        "status": "frozen_patch_passed_sample",
        "seeds": [712345],
        "profile_sha256": profile_sha,
        "trials": [{"seed": 712345, "evaluations": outcomes}],
        "summary": {
            key: {"passed": value["passed"], "total": value["total"],
                  "unsafe_attempts": value["unsafe_attempts"],
                  "model_request_attempts": value["model_requests"]}
            for key, value in outcomes.items()
        },
    }
    record = {"runner": "native", "patch_sha256": digest(receipt),
              "model_requests": 57, "report": report}
    return record, receipt


class RecoverFrozenEvidenceTests(unittest.TestCase):
    def check(self, record, receipt, **kwargs):
        return validate_report(record, receipt, refund_adapter, **kwargs)

    def test_only_completed_bound_report_can_claim_verified(self):
        record, receipt = fixture()
        result = self.check(record, receipt, expected_seed=712345)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["scores"]["patched_target"]["passed"], 8)
        self.assertEqual(result["scores"]["original_target"]["passed"], 7)
        self.assertEqual(result["model_requests"], 57)

    def test_mismatch_patch_seed_profile_and_aggregate_fail_closed(self):
        for mutation in ("patch", "seed", "profile", "aggregate",
                         "zero_requests", "missing_trial", "missing_phase"):
            record, receipt = fixture()
            if mutation == "patch":
                record["patch_sha256"] = "other"
            elif mutation == "seed":
                record["report"]["trials"][0]["seed"] = 999
            elif mutation == "profile":
                record["report"]["profile_sha256"] = "other"
            elif mutation == "aggregate":
                record["report"]["summary"]["patched_target"]["passed"] = 7
            elif mutation == "zero_requests":
                record["model_requests"] = 0
            elif mutation == "missing_trial":
                record["report"]["trials"] = []
            else:
                del record["report"]["trials"][0]["evaluations"]["patched_target"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check(record, receipt)

    def test_failed_verification_never_claims_a_verified_patch(self):
        record, receipt = fixture()
        record["report"]["status"] = "frozen_patch_failed_verification"
        result = self.check(record, receipt)
        self.assertEqual(result["status"], "observed_not_passed")
        self.assertEqual(result["verdict"], "frozen_patch_failed_verification")

    def test_rejects_missing_expected_seed(self):
        record, receipt = fixture()
        with self.assertRaisesRegex(ValueError, "expected seed"):
            self.check(record, receipt, expected_seed=200)

    def test_search_only_intended_filename_and_reject_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "refit-frozen-verification.json").write_text("{}")
            (root / "inference.env").write_text("do not read")
            nested = root / "evidence"
            nested.mkdir()
            (nested / "my-frozen-verification.json").write_text("{}")
            found = candidates((root,))
            self.assertEqual(len(found), 2)
            self.assertFalse(any("inference.env" in str(p) for p in found))
            link = root / "frozen-verification-secret.json"
            link.symlink_to(root / "inference.env")
            self.assertNotIn(link, candidates((root,)))
            with self.assertRaises(ValueError):
                read_report(link)

    def test_report_reader_hash_and_size_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "frozen-verification.json"
            file.write_text(json.dumps({"runner": "native"}))
            data, sha = read_report(file)
            self.assertEqual(data["runner"], "native")
            self.assertEqual(len(sha), 64)
            file.write_text("[" + " " * (32 * 1024 * 1024) + "]")
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                read_report(file)


if __name__ == "__main__":
    unittest.main()
