"""Original mini-SWE-agent, with a brokered model transport and protected tests."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
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
from .verify import METHODS

HERE = Path(__file__).parent
BASE = Path('/opt/task-base')
CACHE = {}


def git(root, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(root),
                                    '-C', str(root), *args], text=True)


def initial_hash(root):
    data = b''
    for name in git(root, 'ls-files', 'requests').splitlines():
        data += name.encode() + b'\0' + (root / name).read_bytes() + b'\0'
    return hashlib.sha256(data).hexdigest()


def outcome_hash(partition, passed):
    return fingerprint({'partition': partition, 'passed': passed, 'checks': len(METHODS[partition])})


def oracle(root, partition):
    p = subprocess.run([sys.executable, '-I', '-S', str(HERE / 'verify.py'), str(root), partition],
                       text=True, capture_output=True, timeout=30)
    try:
        summary = json.loads(p.stdout.splitlines()[-1])
    except (ValueError, IndexError):
        summary = {}
    passed = (p.returncode == 0 and summary.get('completed') is True and
              summary.get('passed') is True and len(summary.get('checks', [])) == len(METHODS[partition]))
    return {'passed': passed, 'returncode': p.returncode, 'checks': summary.get('checks', []),
            'stdout': p.stdout[-16000:], 'stderr': p.stderr[-4000:]}


def describe(config):
    revision = git(Path('/opt/upstream'), 'rev-parse', 'HEAD').strip()
    if revision != config['revision'] or git(BASE, 'rev-parse', 'HEAD').strip() != config['task_revision']:
        raise ValueError('Pinned agent or coding-task checkout changed')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'task'
        shutil.copytree(BASE, root)
        before = {name: oracle(root, name) for name in METHODS}
        if any(result['passed'] for result in before.values()):
            raise ValueError('Unmodified genuine issue must fail each byte-method test partition')
        reference = None
        if config.get('_preflight_patch'):
            subprocess.run(['git', '-C', str(root), 'apply', '-'], input=config['_preflight_patch'],
                           text=True, check=True, capture_output=True)
            reference = {name: oracle(root, name) for name in METHODS}
            if not all(r['passed'] for r in reference.values()):
                raise ValueError('Original upstream fix did not pass the protected tests')
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
                'issue': config['issue'], 'baseline_tests': before, 'reference_tests': reference,
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
    with tempfile.TemporaryDirectory(prefix='mini-task-') as temp:
        root = Path(temp) / 'task'
        shutil.copytree(BASE, root)
        before = initial_hash(root)
        if run is None:
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
            changed = git(root, 'diff', '--name-only').splitlines()
            allowed = (any(n.startswith('requests/') and n.endswith('.py') for n in changed) and
                       all((n.startswith('requests/') and n.endswith('.py')) or n == 'test_requests.py' for n in changed))
            run = {'diff': git(root, 'diff', '--binary'), 'changed_files': changed,
                   'allowed_changes': allowed, 'exit_status': status.get('exit_status'),
                   'trajectory': agent.serialize(), 'error': error}
            CACHE[key] = run
            mode = 'live_original_agent'
        else:
            if run['diff']:
                subprocess.run(['git', '-C', str(root), 'apply', '-'], input=run['diff'],
                               text=True, check=True, capture_output=True)
            mode = 'independent_frozen_code_tests'
        check = oracle(root, partition)
        passed = (check['passed'] and run['allowed_changes'] and
                  run['exit_status'] == 'Submitted' and run['error'] is None)
        result = {'case': 'requests-2316-' + partition, 'passed': passed,
                  'verdict': {'passed': passed, 'unsafe_attempts': 0 if run['allowed_changes'] else 1,
                              'objective_tests': check, 'native_exit_status': run['exit_status']},
                  'error': run['error'], 'trace': run['trajectory']['messages'],
                  'transcript': run['trajectory']['messages'], 'final_text': None,
                  'model_requests': client.requests - count, 'elapsed_seconds': time.monotonic() - started,
                  'initial_db_hash': before, 'final_db_hash': outcome_hash(partition, passed),
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
