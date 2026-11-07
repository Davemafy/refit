"""Host-side boundary checks without importing any external repository."""
import json
from pathlib import Path
import unittest

from scripts.container_agent import command, validate_completion, validate_config
from scripts.migration_engine import AgentContract, AgentProfile, ReplayCase, evaluate


class ContainerAdapterTests(unittest.TestCase):
    def test_no_host_mounts_credentials_network_or_privileges(self):
        args = command('sha256:pinned', 'refit-external-example')
        self.assertEqual(args[args.index('--runtime') + 1], 'runsc')
        self.assertEqual(args[args.index('--network') + 1], 'none')
        self.assertEqual(args[args.index('--user') + 1], '65534:65534')
        self.assertIn('--read-only', args)
        for denied in ('--mount', '-v', '--env-file', '--privileged', '--publish'):
            self.assertNotIn(denied, args)

    def test_completion_model_and_size_bounds(self):
        good = {'model': 'source', 'messages': [{'role': 'user', 'content': 'Hello'}], 'tools': None}
        validate_completion(good, {'source', 'target'})
        for bad in ({**good, 'model': 'unapproved'}, {**good, 'messages': []},
                    {**good, 'tools': [{}] * 129}):
            with self.assertRaises(ValueError):
                validate_completion(bad, {'source', 'target'})

    def test_manifest_caps_all_model_requests(self):
        config = json.loads((Path(__file__).resolve().parents[1] /
            'integrations/retail/manifest.json').read_text())
        validate_config(config)
        with self.assertRaises(ValueError):
            validate_config({**config, 'max_requests': 401})

    def test_original_runner_hook_retains_shared_engine_scoring(self):
        seen = []
        def native(client, model, contract, profile, case):
            seen.append((model, profile.instructions))
            return {'case': case.name, 'passed': False, 'verdict': {'unsafe_attempts': 0},
                    'error': None, 'trace': [], 'model_requests': 7, 'elapsed_seconds': .1}
        result = evaluate(None, 'target', AgentContract('external', (), ()),
                          AgentProfile('Original instructions'), [ReplayCase('original', 'request', runner=native)])
        self.assertEqual(result['passed'], 0)
        self.assertEqual(result['model_requests'], 7)
        self.assertEqual(seen, [('target', 'Original instructions')])
