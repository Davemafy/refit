"""Check the retained failed real run offline; never import upstream on host."""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MiniSweEvidenceTests(unittest.TestCase):
    def test_real_failure_withholds_export_and_stays_within_budget(self):
        raw = gzip.decompress((ROOT / 'data/evaluations/mini-swe-requests-2316-001.json.gz').read_bytes())
        record = json.loads(raw)
        self.assertEqual(record['engine_revision']['commit'], '3cd13cc5709ae9bae1555da48540d0167dff9e36')
        self.assertEqual(record['model_requests'], 35)
        self.assertEqual(record['logical_requests'], 35)
        self.assertEqual(len(record['completions']), 35)
        self.assertTrue(all(c['status'] == 'completed' for c in record['completions']))
        self.assertLessEqual(record['model_requests'], record['config']['max_requests'])
        self.assertEqual(record['config']['max_requests'], 96)
        source, target, trial = record['native_cases']
        self.assertEqual([c['model_requests'] for c in (source, target, trial)], [10, 12, 12])
        self.assertTrue(source['passed'])
        self.assertEqual(source['verdict']['native_exit_status'], 'Submitted')
        self.assertFalse(target['passed'])
        self.assertTrue(target['verdict']['objective_tests']['passed'])
        self.assertEqual(target['verdict']['native_exit_status'], 'LimitsExceeded')
        self.assertFalse(trial['passed'])
        self.assertEqual(trial['changed_files'], [])
        self.assertEqual(record['result']['status'], 'repair_rejected_training')
        self.assertIsNone(record['result']['export'])
        self.assertIsNone(record['result']['original_runner_verification'])
        self.assertFalse(record['verified'])
        self.assertEqual(record['actual_runtime'], 'runsc')
        self.assertEqual(record['container_state']['ExitCode'], 0)
        self.assertFalse(record['container_state']['OOMKilled'])
        self.assertTrue(record['cleanup']['verified'])
        for case, label in zip((source, target, trial), ('source', 'replacement', 'repair-trial')):
            self.assertEqual(case['code_diff'], (ROOT / 'integrations/mini_swe/evidence' / (label + '.patch')).read_text())
        self.assertIn(hashlib.sha256(raw).hexdigest(), (ROOT / 'integrations/mini_swe/README.md').read_text())
        preflight = json.loads(gzip.decompress((ROOT / 'data/evaluations/mini-swe-requests-2316-preflight.json.gz').read_bytes()))
        self.assertEqual(preflight['model_requests'], 0)
        metadata = preflight['description']['metadata']
        self.assertTrue(all(not r['passed'] for r in metadata['baseline_tests'].values()))
        self.assertTrue(all(r['passed'] for r in metadata['reference_tests'].values()))
        self.assertTrue(preflight['cleanup']['verified'])
