"""Replay three original upstream tau2 mock-domain task tickets and tools.

Uses the upstream goal actions on a separate database as a state oracle. This
is a small integration smoke suite, not the full conversational tau2 benchmark.
"""
import json

from tau2.agent.llm_agent import LLMAgent
from tau2.domains.mock.data_model import get_db
from tau2.domains.mock.environment import get_environment
from tau2.domains.mock.tools import MockTools
from tau2.domains.mock.utils import MOCK_TASK_SET_PATH

from .migration_engine import AgentContract, AgentProfile, ReplayCase, evaluate

TASK_IDS = ("create_task_1_with_env_assertions", "update_task_1", "impossible_task_1")


class UpstreamFixture:
    def __init__(self, task):
        self.task = task
        self.tools = MockTools(get_db())
        self.reference = MockTools(get_db())
        for action in task["evaluation_criteria"]["actions"]:
            self.reference.use_tool(action["name"], **action["arguments"])
        self.events = []
        self.unsafe_attempts = 0

    def call(self, name, arguments):
        before = self.tools.db.model_dump(mode="json")
        if name not in self.tools.get_tools():
            self.unsafe_attempts += 1
            result = {"error": "unknown tool"}
        else:
            try:
                result = self.tools.use_tool(name, **arguments)
                if hasattr(result, "model_dump"):
                    result = result.model_dump(mode="json")
                elif isinstance(result, list):
                    result = [x.model_dump(mode="json") if hasattr(x, "model_dump") else x
                              for x in result]
                elif isinstance(result, str):
                    result = {"message": result}
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        self.events.append({"tool": name, "arguments": arguments, "result": result,
                            "before": before, "after": self.tools.db.model_dump(mode="json")})
        return result

    def verify(self):
        equal_state = (self.tools.db.model_dump(mode="json") ==
                       self.reference.db.model_dump(mode="json"))
        assertions = self.task["evaluation_criteria"].get("env_assertions", [])
        try:
            assertions_ok = all(getattr(self.tools, a["func_name"])(**a["arguments"])
                                for a in assertions)
        except (ValueError, KeyError):
            assertions_ok = False
        transfer_required = any(a["name"] == "transfer_to_human_agents"
                                for a in self.task["evaluation_criteria"]["actions"])
        transferred = any(e["tool"] == "transfer_to_human_agents" and
                          not (isinstance(e["result"], dict) and e["result"].get("error"))
                          for e in self.events)
        return {"passed": equal_state and assertions_ok and
                (not transfer_required or transferred) and not self.unsafe_attempts,
                "unsafe_attempts": self.unsafe_attempts,
                "upstream_goal_state_matches": equal_state,
                "upstream_assertions_pass": assertions_ok,
                "required_transfer_completed": not transfer_required or transferred}


def verify_upstream_fixtures(client, source, target):
    toolkit = MockTools(get_db())
    tools = list(toolkit.get_tools().values())
    policy = get_environment().get_policy()
    profile = AgentProfile(LLMAgent(tools=tools, domain_policy=policy, llm=source).system_prompt)
    contract = AgentContract("tau2_original_mock_tasks",
                             tuple(tool.openai_schema for tool in tools), (policy,))
    tasks = json.loads(MOCK_TASK_SET_PATH.read_text())
    selected = [t for t in tasks if t["id"] in TASK_IDS]
    assert len(selected) == len(TASK_IDS)
    cases = [ReplayCase(t["id"], t["ticket"], lambda task=t: UpstreamFixture(task))
             for t in selected]
    source_result = evaluate(client, source, contract, profile, cases)
    target_result = evaluate(client, target, contract, profile, cases)
    passed = all(r["passed"] == r["total"] and not r["unsafe_attempts"]
                 for r in (source_result, target_result))
    return {"status": "passed" if passed else "failed", "source": source_result,
            "target": target_result, "task_ids": list(TASK_IDS),
            "scope": "Original upstream tickets, agent, policy, tool functions and goal actions; "
                     "single-request smoke evaluation, not a full tau2 benchmark run."}
