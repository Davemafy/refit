"""Optional integration with the unmodified upstream tau2 LLMAgent runner.

Install the pinned integration requirements first. Models still use Refit's
bounded Vultr transport; business tools still use the approved replay gateway.
Only the upstream runner's provider seam is replaced, under a process-local lock.
"""
from __future__ import annotations

import json
import threading
from unittest.mock import patch

_LOCK = threading.RLock()
TAU2_COMMIT = "033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f"


class Tau2Client:
    """Run each agent step through tau2's original generate_next_message method."""
    def __init__(self, client):
        from tau2.agent import llm_agent
        from tau2.data_model import message
        from tau2.environment.tool import BaseTool
        from tau2.utils.llm_utils import to_litellm_messages

        class SchemaTool(BaseTool):
            schema_value: dict

            @property
            def openai_schema(self):
                return self.schema_value

            def _call(self, *args, **kwargs):
                raise RuntimeError("Business tool execution belongs to the replay gateway")

        self.client = client
        self.module = llm_agent
        self.messages = message
        self.tool_class = SchemaTool
        self.to_api = to_litellm_messages
        self.runner_steps = 0

    @property
    def requests(self):
        return self.client.requests

    def _message(self, value):
        kind = value["role"]
        if kind == "tool":
            return self.messages.ToolMessage(role="tool", id=value["tool_call_id"],
                                             content=value.get("content"))
        if kind == "assistant":
            calls = []
            for call in value.get("tool_calls") or []:
                function = call["function"]
                arguments = function["arguments"]
                calls.append(self.messages.ToolCall(
                    id=call["id"], name=function["name"],
                    arguments=json.loads(arguments) if isinstance(arguments, str) else arguments))
            return self.messages.AssistantMessage(
                role="assistant", content=value.get("content"), tool_calls=calls or None)
        return self.messages.UserMessage(role="user", content=value["content"])

    def complete(self, model, messages, tools=None):
        if tools is None:
            # Repair generation is not a business agent step.
            return self.client.complete(model, messages, max_tokens=2500)
        schemas = [self.tool_class(name=t["function"]["name"], schema_value=t)
                   for t in tools]
        agent = self.module.LLMAgent(tools=schemas, domain_policy="", llm=model)
        history = [self._message(value) for value in messages[1:]]
        state = agent.get_init_state(message_history=history[:-1])
        # This is the exported agent configuration, including its exact prompt.
        state.system_messages = [self.messages.SystemMessage(
            role="system", content=messages[0]["content"])]

        def provider(*, model, tools, messages, **kwargs):
            response = self.client.complete(model, self.to_api(messages),
                                             [tool.openai_schema for tool in tools])
            return self._message(response)

        with _LOCK, patch.object(self.module, "generate", provider):
            response, state = agent.generate_next_message(history[-1], state)
            self.runner_steps += 1
        return self.to_api([response])[0]
