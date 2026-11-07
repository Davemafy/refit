"""Produce ordinary mini-SWE-agent YAML from the verified Refit export."""
import copy
import hashlib
import json
from pathlib import Path

import minisweagent
import yaml
from minisweagent.models.utils.actions_toolcall import BASH_TOOL


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def baseline():
    return yaml.safe_load((Path(minisweagent.__file__).parent / 'config/mini.yaml').read_text())


def contract_values():
    original = baseline()
    return {'name': 'mini_swe_original', 'tools': [BASH_TOOL],
            'policies': [original['agent']['instance_template'],
                         'Only system_template may be adapted. Bash tool descriptions and schemas are immutable.']}


def configuration(model, profile, step_limit=12):
    if profile['tool_descriptions']:
        raise ValueError('Original bash tool contract is immutable')
    config = copy.deepcopy(baseline())
    config['agent'].update(agent_class='default', system_template=profile['instructions'],
                           step_limit=step_limit, cost_limit=0, wall_time_limit_seconds=240)
    config['model'].update(model_class='litellm', model_name='openai/' + model,
                           cost_tracking='ignore_errors')
    config['model']['model_kwargs'].update(api_base='https://api.vultrinference.com/v1',
                                          temperature=0, num_retries=0)
    return config


def from_export(exported):
    if digest({k:v for k,v in exported.items() if k != 'integrity_sha256'}) != exported['integrity_sha256']:
        raise ValueError('Export integrity mismatch')
    original = baseline()
    if digest({'instructions': original['agent']['system_template'], 'tool_descriptions': {}}) != exported['baseline_sha256']:
        raise ValueError('Original system template changed')
    if digest(contract_values()) != exported['contract_sha256']:
        raise ValueError('Original tool or task contract changed')
    return configuration(exported['model'], exported['target_profile'])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(yaml.safe_dump(from_export(json.loads(args.export.read_text())), sort_keys=False))
