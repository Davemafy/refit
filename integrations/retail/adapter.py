"""Upstream retail agent, customer, orchestrator, tools, data and evaluator.

Import ONLY in the isolated image. The host never imports this module.
"""
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from loguru import logger
from tau2.agent import llm_agent
from tau2.data_model.message import AssistantMessage, ToolCall, ToolMessage
from tau2.data_model.semantic_communication import CommunicateScoring
from tau2.domains.retail.environment import get_environment, get_tasks
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.user import user_simulator
from tau2.utils.llm_utils import to_litellm_messages

from scripts.migration_engine import AgentContract, AgentProfile, ReplayCase, fingerprint
from .apply_config import agent_from_export, build_agent

logger.remove()
ROOT = Path('/opt/upstream')


def describe(config):
    actual = subprocess.check_output(['git', '-c', 'safe.directory=/opt/upstream',
                                      '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != config['revision']:
        raise ValueError('Upstream checkout revision mismatch')
    tasks = {t.id: t for t in get_tasks(None)}
    ids = sum(config['splits'].values(), [])
    if len(set(ids)) != len(ids) or any(not x for x in config['splits'].values()):
        raise ValueError('Task splits must be nonempty and disjoint')
    env = get_environment()
    contract = AgentContract('tau2_retail_original', tuple(t.openai_schema for t in env.get_tools()),
                             (env.get_policy(),))
    metadata = {'upstream_revision': actual, 'original_model_default': 'upstream CLI configurable',
                'policy_sha256': fingerprint(env.get_policy()), 'splits': {}}
    for split, names in config['splits'].items():
        rows = []
        for name in names:
            task = tasks[name]
            criteria = task.evaluation_criteria
            # Select state-verifiable original tasks; never drop criteria from
            # an individual task or feed reference actions to the agent.
            if not criteria or not criteria.actions or criteria.nl_assertions or criteria.communicate_info:
                raise ValueError('Selected task requires unsupported non-state criteria')
            if task.initial_state is not None:
                raise ValueError('This first adapter requires default database initialization')
            reference = get_environment()
            for action in criteria.actions:
                reference.make_tool_call(tool_name=action.name, requestor=action.requestor,
                                         **action.arguments)
            if reference.get_db_hash() == env.get_db_hash():
                raise ValueError('Expected task must change business state')
            rows.append({'id': name, 'case_name': 'upstream-retail-' + name,
                         'task_sha256': fingerprint(task.model_dump(mode='json')),
                         'initial_db_hash': env.get_db_hash(),
                         'expected_db_hash': reference.get_db_hash()})
        metadata['splits'][split] = rows
    return contract, AgentProfile(llm_agent.AGENT_INSTRUCTION), metadata


def cases(config, split):
    tasks = {t.id: t for t in get_tasks(None)}
    return [ReplayCase(name='upstream-retail-' + name,
                       request=str(tasks[name].user_scenario),
                       runner=lambda client, model, contract, profile, case, task=tasks[name]:
                           run_case(client, model, profile, task, config))
            for name in config['splits'][split]]


def run_case(client, model, profile, task, config, exported=None):
    env = get_environment()
    initial = env.get_db_hash()
    count = client.requests
    started = time.monotonic()
    requests = []

    def provider(*, model, messages, tools=None, **kwargs):
        value = client.complete(model, to_litellm_messages(messages),
                                [t.openai_schema for t in tools] if tools else None)
        requests.append({'model': model, 'message': value})
        calls = [ToolCall(id=c['id'], name=c['function']['name'],
                         arguments=json.loads(c['function']['arguments'])
                         if isinstance(c['function']['arguments'], str)
                         else c['function']['arguments']) for c in value.get('tool_calls') or []]
        return AssistantMessage(role='assistant', content=value.get('content'),
                                tool_calls=calls or None, cost=0.0)

    agent = (agent_from_export(env, exported) if exported else
             build_agent(env, model, {'instructions': profile.instructions,
                                     'tool_descriptions': dict(profile.tool_descriptions)}))
    user = user_simulator.UserSimulator(llm=config['user_model'], instructions=str(task.user_scenario))
    orchestrator = Orchestrator(domain='retail', agent=agent, user=user, environment=env,
                                task=task, max_steps=config['max_steps'], max_errors=3,
                                seed=config['seed'], timeout=300)
    error = None
    simulation = None
    reward = None
    try:
        with patch.object(llm_agent, 'generate', provider), patch.object(user_simulator, 'generate', provider):
            simulation = orchestrator.run()
        reward = evaluate_simulation(simulation, task, EvaluationType.ALL, solo_mode=False,
                                     domain='retail', communicate_scoring=CommunicateScoring())
        simulation.reward_info = reward
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:250]
    messages = simulation.messages if simulation else []
    tool_errors = sum(bool(m.error) for m in messages if isinstance(m, ToolMessage))
    passed = error is None and reward is not None and reward.reward == 1.0 and not tool_errors
    return {'case': 'upstream-retail-' + task.id, 'passed': passed,
            'verdict': {'passed': passed, 'unsafe_attempts': tool_errors,
                        'unsafe_attempts_definition': 'Upstream tool errors conservatively counted',
                        'reward': reward.model_dump(mode='json') if reward else None},
            'error': error, 'trace': [m.model_dump(mode='json') for m in messages if isinstance(m, ToolMessage)],
            'transcript': [m.model_dump(mode='json') for m in messages],
            'final_text': None, 'model_requests': client.requests - count,
            'elapsed_seconds': time.monotonic() - started,
            'initial_db_hash': initial, 'final_db_hash': env.get_db_hash(),
            'native_model_responses': requests,
            'termination_reason': str(simulation.termination_reason) if simulation else None}


def verify_export(client, config, exported):
    tasks = {t.id: t for t in get_tasks(None)}
    results = [run_case(client, config['target'], None, tasks[name], config, exported=exported)
               for name in config['splits']['holdout']]
    return {'passed': all(r['passed'] for r in results), 'runner': 'tau2.Orchestrator',
            'uses_exported_configuration': True, 'cases': results,
            'model_requests': sum(r['model_requests'] for r in results)}
