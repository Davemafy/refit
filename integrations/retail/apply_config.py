"""Apply exported configuration in the original tau2 runner; no Refit imports."""
import hashlib
import json

from tau2.agent.llm_agent import AGENT_INSTRUCTION, LLMAgent, SYSTEM_PROMPT
from tau2.environment.tool import BaseTool


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ConfiguredTool(BaseTool):
    schema_value: dict

    @property
    def openai_schema(self):
        return self.schema_value

    def _call(self, *args, **kwargs):
        raise RuntimeError("Original tau2 Environment owns tool execution")


class ConfiguredAgent(LLMAgent):
    instruction_text = AGENT_INSTRUCTION

    @property
    def system_prompt(self):
        return SYSTEM_PROMPT.format(agent_instruction=self.instruction_text,
                                    domain_policy=self.domain_policy)


def build_agent(environment, model, profile):
    overrides = profile["tool_descriptions"]
    tools = []
    for original in environment.get_tools():
        schema = json.loads(json.dumps(original.openai_schema))
        name = schema["function"]["name"]
        if name in overrides:
            schema["function"]["description"] = overrides[name]
        tools.append(ConfiguredTool(name=name, schema_value=schema))
    if set(overrides) - {t.name for t in tools}:
        raise ValueError("Patch refers to an unknown original tool")
    agent = ConfiguredAgent(tools=tools, domain_policy=environment.get_policy(), llm=model)
    agent.instruction_text = profile["instructions"]
    return agent


def agent_from_export(environment, exported):
    body = {k: v for k, v in exported.items() if k != "integrity_sha256"}
    if digest(body) != exported.get("integrity_sha256"):
        raise ValueError("Export integrity mismatch")
    if exported["format"] != "refit.native-config.v1" or exported["domain"] != "retail":
        raise ValueError("Unsupported configuration")
    baseline = {"instructions": AGENT_INSTRUCTION, "tool_descriptions": {}}
    if digest(baseline) != exported["baseline_sha256"]:
        raise ValueError("Original agent instructions changed")
    contract = {"name": "tau2_retail_original", "tools": [
        t.openai_schema for t in environment.get_tools()],
        "policies": [environment.get_policy()]}
    if digest(contract) != exported["contract_sha256"]:
        raise ValueError("Original policy or tool contract changed")
    return build_agent(environment, exported["model"], exported["target_profile"])
