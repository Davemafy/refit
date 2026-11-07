"""Read preserved real evidence only; never import the external agent on host."""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from scripts.container_agent import validate_result


ROOT = Path(__file__).resolve().parents[1]


class OriginalRetailEvidenceTests(unittest.TestCase):
    def test_real_comparison_and_fresh_export_acceptance(self):
        def load(name):
            return json.loads(gzip.decompress((ROOT / 'data/evaluations' / name).read_bytes()))
        primary = load('retail-native-001-partial.json.gz')
        recovered = load('retail-native-001-recovered.json.gz')
        fresh = load('retail-native-export-fresh-2026-11-07.json.gz')
        self.assertEqual(primary['model_requests'], 208)
        self.assertEqual(len(primary['completions']), 208)
        self.assertEqual(sum(c['model_requests'] for c in primary['native_cases']), 208)
        self.assertEqual(len(primary['native_cases']), 14)
        self.assertTrue(all(c['passed'] for c in primary['native_cases']))
        self.assertEqual(recovered['mode'], 'recorded_transport_recovery')
        self.assertEqual(recovered['model_requests'], 0)
        self.assertEqual(recovered['logical_requests'], 208)
        for original, replay in zip(primary['completions'], recovered['completions']):
            self.assertEqual(original['status'], 'completed')
            self.assertEqual(replay['status'], 'replayed')
            self.assertEqual(original['request_sha256'], replay['request_sha256'])
            self.assertEqual(original['response'], replay['response'])
        validate_result(recovered['result'], recovered['description'], recovered['config'])
        self.assertEqual(recovered['result']['status'], 'compatible_on_sample')
        phases = recovered['result']['report']['evaluations']
        for name in ('source_training', 'target_training', 'source_validation',
                     'validation', 'source_holdout', 'original_holdout'):
            self.assertEqual((phases[name]['passed'], phases[name]['total']), (2, 2))
        self.assertEqual(fresh['mode'], 'fresh_export_verification')
        self.assertEqual(fresh['model_requests'], 33)
        self.assertEqual(fresh['logical_requests'], 33)
        self.assertTrue(all(c['status'] == 'completed' for c in fresh['completions']))
        validate_result(fresh['result'], fresh['description'], fresh['config'], verification_only=True)
        self.assertEqual(len(fresh['result']['original_runner_verification']['cases']), 2)
        self.assertEqual(primary['model_requests'] + fresh['model_requests'], 241)
        self.assertLessEqual(241, 400)
        for record in (recovered, fresh):
            self.assertIs(record['verified'], True)
            self.assertEqual(record['actual_runtime'], 'runsc')
            self.assertEqual(record['container_state']['ExitCode'], 0)
            self.assertIs(record['container_state']['OOMKilled'], False)
            self.assertIs(record['cleanup']['verified'], True)
        raw_export = (ROOT / 'integrations/retail/verified/agent-config.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw_export).hexdigest(),
                         'ec7e9b87a6c64fae3141755a136bf62be3a6f6225943e26fa23fbe98cfbf49e8')
        exported = json.loads(raw_export)
        self.assertEqual(exported, fresh['result']['export'])
        self.assertEqual(exported, recovered['result']['export'])
        self.assertEqual(exported['model'], 'glm-5.2')
        self.assertIsNone(exported['compatibility_receipt'])
