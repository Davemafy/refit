"""Original mini-SWE-agent, with a brokered model transport and protected tests."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from unittest.mock import patch

import litellm
import yaml
from minisweagent.agents import get_agent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models import get_model
from minisweagent.models.litellm_model import LitellmModel

from scripts.migration_engine import AgentContract, AgentProfile, ReplayCase, fingerprint
from .apply_config import baseline, configuration, contract_values, from_export

HERE = Path(__file__).parent
BASE = Path('/opt/task-base')
CACHE = {}
CHECK_COUNTS = {"training": 1, "validation": 2, "holdout": 4}


def git(root, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(root),
                                    '-C', str(root), *args], text=True)


def initial_hash(root):
    data = b''
    for name in git(root, 'ls-files', 'requests').splitlines():
        data += name.encode() + b'\0' + (root / name).read_bytes() + b'\0'
    return hashlib.sha256(data).hexdigest()


def outcome_hash(partition, passed):
    return fingerprint({'partition': partition, 'passed': passed, 'checks': CHECK_COUNTS[partition]})


def describe(config):
    revision = git(Path('/opt/upstream'), 'rev-parse', 'HEAD').strip()
    if revision != config['revision'] or git(BASE, 'rev-parse', 'HEAD').strip() != config['task_revision']:
        raise ValueError('Pinned agent or coding-task checkout changed')
    # Check through the same bash environment the original agent uses.
    env = LocalEnvironment(cwd='/opt/refit', timeout=10)
    isolation = env.execute({'command': (
        'test ! -e integrations/mini_swe/evaluation_cases.json && '
        'test ! -e integrations/mini_swe/evidence && '
        'test ! -e experiments/mini-swe-reference.patch && test ! -e .git'
    )})
    if isolation['returncode'] != 0:
        raise ValueError('Protected evaluation material is present in generation')
    values = contract_values()
    # Exercise the upstream parser, not a substitute agent or model success.
    probe = get_model(config=configuration(config['source'], {
        'instructions': baseline()['agent']['system_template'], 'tool_descriptions': {}})['model'])
    parsed = probe._parse_actions(litellm.ModelResponse(choices=[{'index': 0,
        'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
        'tool_calls': [{'id': 'preflight', 'type': 'function', 'function': {
            'name': 'bash', 'arguments': '{"command":"pwd"}'}}]}}]))
    if parsed[0]['command'] != 'pwd':
        raise ValueError('Original model parser protocol failed')
    contract = AgentContract(values['name'], tuple(values['tools']), tuple(values['policies']))
    profile = AgentProfile(baseline()['agent']['system_template'])
    metadata = {'upstream_revision': revision, 'task_revision': config['task_revision'],
                'issue': config['issue'], 'hidden_fixture_absence_checked': True,
                'splits': {split: [{'case_name': 'requests-2316-' + partition,
                    'initial_db_hash': initial_hash(BASE),
                    'expected_db_hash': outcome_hash(partition, True)} for partition in parts]
                    for split, parts in config['splits'].items()}}
    return contract, profile, metadata


def cases(config, split):
    return [ReplayCase('requests-2316-' + partition, config['problem_statement'],
                       runner=lambda client, model, contract, profile, case, part=partition:
                           run_case(client, model, profile, config, part))
            for partition in config['splits'][split]]


def run_case(client, model_name, profile, config, partition, native_config=None, fresh=False):
    started = time.monotonic()
    count = client.requests
    key = fingerprint({'model': model_name, 'instructions': profile.instructions if profile else native_config,
                       'descriptions': dict(profile.tool_descriptions) if profile else {}})
    error = None
    run = CACHE.get(key) if not fresh else None
    if run is None:
        with tempfile.TemporaryDirectory(prefix='mini-task-') as temp:
            root = Path(temp) / 'task'
            shutil.copytree(BASE, root)
            native = copy.deepcopy(native_config) if native_config else configuration(
                model_name, {'instructions': profile.instructions,
                             'tool_descriptions': dict(profile.tool_descriptions)}, config['step_limit'])
            env = LocalEnvironment(cwd=str(root), timeout=25, env={
                **native['environment'].get('env', {}), 'PYTHONPATH': str(HERE)})
            original_model = get_model(config=native['model'])
            agent = get_agent(original_model, env, native['agent'])

            def provider(instance, messages, **kwargs):
                clean = [{k:v for k,v in m.items() if k in
                          ('role','content','tool_calls','tool_call_id','name')} for m in messages]
                from minisweagent.models.utils.actions_toolcall import BASH_TOOL
                reply = client.complete(instance.config.model_name.removeprefix('openai/'), clean, [BASH_TOOL])
                return litellm.ModelResponse(model=instance.config.model_name,
                    choices=[{'index': 0, 'message': reply,
                              'finish_reason': 'tool_calls' if reply.get('tool_calls') else 'stop'}])

            status = {}
            try:
                with patch.object(LitellmModel, '_query', provider):
                    status = agent.run(config['problem_statement'])
            except Exception as exc:
                error = type(exc).__name__ + ': ' + str(exc)[:200]
            changed = git(root, 'diff', '--name-only', config['task_revision']).splitlines()
            allowed = (any(n.startswith('requests/') and n.endswith('.py') for n in changed) and
                       all((n.startswith('requests/') and n.endswith('.py')) or n == 'test_requests.py' for n in changed))
            run = {'diff': git(root, 'diff', '--binary', config['task_revision']), 'changed_files': changed,
                   'allowed_changes': allowed, 'exit_status': status.get('exit_status'),
                   'trajectory': agent.serialize(), 'error': error}
            CACHE[key] = run
        mode = 'live_original_agent'
    else:
        mode = 'independent_frozen_code_tests'
    check = client.evaluate_patch(partition, run['diff'])
    passed = (check['passed'] and run['allowed_changes'] and
              run['exit_status'] == 'Submitted' and run['error'] is None)
    verdict = {'passed': passed, 'unsafe_attempts': int(bool(run['changed_files']) and not run['allowed_changes']),
               'objective_tests': check, 'native_exit_status': run['exit_status']}
    if run['exit_status'] == 'LimitsExceeded':
        verdict['repair_hint'] = (
            'Preserve the mandatory standalone submission command and 12-step limit. '
            'Change only system instructions. Budget actions up front: locate the fault, '
            'make the smallest source edit early, run the task-provided verifier, then '
            'submit. Reserve at least one action for submission. Avoid optional suites, '
            'dependency installs and repeated investigation in the offline environment.'
        )
    result = {'case': 'requests-2316-' + partition, 'passed': passed,
              'verdict': verdict, 'error': run['error'], 'trace': run['trajectory']['messages'],
              'transcript': run['trajectory']['messages'], 'final_text': None,
              'model_requests': client.requests - count, 'elapsed_seconds': time.monotonic() - started,
              'initial_db_hash': initial_hash(BASE), 'final_db_hash': outcome_hash(partition, passed),
              'code_diff': run['diff'], 'changed_files': run['changed_files'], 'execution_mode': mode}
    client.record_case(result)
    return result


def verify_export(client, config, exported):
    native = from_export(exported)
    text = yaml.safe_dump(native, sort_keys=False)
    loaded = yaml.safe_load(text)
    results = [run_case(client, config['target'], None, config, partition,
                        native_config=loaded, fresh=True) for partition in config['splits']['holdout']]
    return {'passed': all(r['passed'] for r in results), 'uses_exported_configuration': True,
            'runner': 'minisweagent.agents.default.DefaultAgent', 'cases': results,
            'model_requests': sum(r['model_requests'] for r in results), 'configuration_yaml': text}
