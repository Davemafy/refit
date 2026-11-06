"""Execute the real optional upstream runner; ordinary unit tests stay dependency-free."""
import os
import unittest
from unittest.mock import patch

from scripts import refund_adapter
from scripts.migration_engine import evaluate
from tests.test_refit_adapters import SyntheticRefundResponder


@unittest.skipUnless(os.getenv("REFIT_TEST_TAU2") == "1", "optional tau2 runner integration")
class Tau2IntegrationTests(unittest.TestCase):
    def test_original_fixture_goals_are_verified_against_original_tools(self):
        import json
        from tau2.domains.mock.utils import MOCK_TASK_SET_PATH
        from scripts.tau2_fixtures import TASK_IDS, UpstreamFixture
        tasks = json.loads(MOCK_TASK_SET_PATH.read_text())
        for task in tasks:
            if task["id"] not in TASK_IDS:
                continue
            with self.subTest(task=task["id"]):
                fixture = UpstreamFixture(task)
                self.assertFalse(fixture.verify()["passed"])
                for action in task["evaluation_criteria"]["actions"]:
                    fixture.call(action["name"], action["arguments"])
                self.assertTrue(fixture.verify()["passed"], fixture.events)

    def test_unmodified_upstream_runner_executes_stateful_refund_workflows(self):
        from tau2.agent.llm_agent import LLMAgent
        from scripts.tau2_bridge import Tau2Client
        from tau2.agent import llm_agent
        original_generate = llm_agent.generate
        method = LLMAgent.generate_next_message
        steps = []

        def observed(agent, *args, **kwargs):
            steps.append(agent)
            return method(agent, *args, **kwargs)

        client = Tau2Client(SyntheticRefundResponder())
        with patch.object(LLMAgent, "generate_next_message", observed):
            result = evaluate(client, "source", refund_adapter.CONTRACT,
                              refund_adapter.BASE_PROFILE,
                              refund_adapter.make_cases(811, "holdout"))
        self.assertEqual(result["passed"], 8, result["cases"])
        self.assertEqual(result["unsafe_attempts"], 0)
        self.assertEqual(len(steps), client.runner_steps)
        self.assertGreater(len(steps), 8)
        self.assertIs(llm_agent.generate, original_generate)

    def test_transport_failure_restores_upstream_provider(self):
        from tau2.agent import llm_agent
        from scripts.tau2_bridge import Tau2Client
        class Failing:
            def complete(self, *args, **kwargs):
                raise RuntimeError("provider unavailable")
        client = Tau2Client(Failing())
        original = llm_agent.generate
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            client.complete("source", [
                {"role": "system", "content": "Do the task."},
                {"role": "user", "content": "Refund ORD-1234567"},
            ], refund_adapter.CONTRACT.schemas(refund_adapter.BASE_PROFILE))
        self.assertIs(llm_agent.generate, original)


if __name__ == "__main__":
    unittest.main()
