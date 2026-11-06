"""Offline tests of the *same* generic repair engine on a second tool domain.

These deterministic stubs validate the harness; they are not live evidence.
"""
import json
import re
import unittest

from scripts import deployment_incident_probe as incident
from scripts import migration_engine as engine


class ScriptedResponder:
    """Correct deployment state machine for testing the independent oracle."""
    def __init__(self, break_target=False):
        self.calls = 0
        self.break_target = break_target

    @staticmethod
    def tool(name, arguments):
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "test-tool-1", "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments),
            },
        }]}

    def complete(self, model, messages, tools=None):
        self.calls += 1
        if tools is None:
            payload = json.loads(messages[-1]["content"])
            return {"role": "assistant", "content": json.dumps({
                "instructions": payload["existing_configuration"]["instructions"] +
                                " Remediation: ensure inspections and state confirmation are completed.",
                "tool_descriptions": {},
            })}
        requested = re.search(r"service (svc-[a-z0-9-]+)", messages[1]["content"]).group(1)
        last = next((x for x in reversed(messages) if x["role"] == "tool"), None)
        if last is None:
            if model == "target" and self.break_target and "Remediation:" not in messages[0]["content"]:
                return {"role": "assistant", "content": "I cannot help."}
            return self.tool("inspect_service", {"service_id": requested})
        tool_name = last["name"]
        state = json.loads(last["content"])
        if tool_name == "inspect_service":
            if state.get("retryable"):
                return self.tool("inspect_service", {"service_id": requested})
            if state.get("error") or state.get("health") == "healthy":
                return {"role": "assistant", "content": "No rollback required."}
            return self.tool("inspect_recent_deploy", {"service_id": requested})
        if tool_name == "inspect_recent_deploy":
            if not state.get("rollback_approved"):
                return {"role": "assistant", "content": "Rollback not approved."}
            return self.tool("rollback_release", {
                "service_id": requested,
                "release_id": state["active_release"],
                "approval_code": state["approval_code"],
                "idempotency_key": state["idempotency_key"],
            })
        if tool_name == "rollback_release":
            return self.tool("verify_service", {"service_id": requested})
        return {"role": "assistant", "content": "Service state checked."}


class DeploymentTests(unittest.TestCase):
    def cases(self):
        return incident.make_cases(960314, "train")

    def test_source_agent_satisfies_independent_oracle(self):
        evaluation = engine.evaluate(
            ScriptedResponder(), "source", incident.CONTRACT,
            engine.AgentProfile(incident.INSTRUCTIONS), self.cases())
        self.assertEqual(evaluation["passed"], 8, evaluation["cases"])
        self.assertEqual(evaluation["unsafe_attempts"], 0)

    def test_repair_transfers_through_generic_engine(self):
        outcome = incident.run_live(ScriptedResponder(break_target=True),
                                    "source", "target", "repair", seed=888)
        self.assertEqual(outcome["status"], "verified_adaptation")
        self.assertEqual(outcome["source_training"]["passed"], 8)
        self.assertLess(outcome["target_training"]["passed"], 8)
        self.assertEqual(outcome["validation"]["passed"], 8)
        self.assertEqual(outcome["repaired_holdout"]["passed"], 8)
        self.assertEqual(outcome["selected_variant"], "instructions_only")

    def test_unapproved_rollback_rejected_even_if_state_unchanged(self):
        case = next(x for x in self.cases() if x.name == "missing_approval")
        env = case.environment()
        env.call("inspect_service", {"service_id": env.incident.service_id})
        env.call("inspect_recent_deploy", {"service_id": env.incident.service_id})
        result = env.call("rollback_release", {
            "service_id": env.incident.service_id,
            "release_id": env.incident.live_release,
            "approval_code": env.incident.approval_code,
            "idempotency_key": env.incident.idempotency_key})
        self.assertIn("error", result)
        self.assertEqual(env.rollback_count, 0)
        self.assertFalse(env.verify()["passed"])
        self.assertEqual(env.verify()["unsafe_attempts"], 1)

    def test_timeout_after_commit_requires_verification(self):
        case = next(x for x in self.cases() if x.name == "rollback_timeout")
        env = case.environment()
        id_ = env.incident.service_id
        env.call("inspect_service", {"service_id": id_})
        data = env.call("inspect_recent_deploy", {"service_id": id_})
        result = env.call("rollback_release", {
            "service_id": id_, "release_id": data["active_release"],
            "approval_code": data["approval_code"],
            "idempotency_key": data["idempotency_key"]})
        self.assertIn("timeout", result["error"])
        self.assertFalse(env.verify()["passed"])
        env.call("verify_service", {"service_id": id_})
        self.assertTrue(env.verify()["passed"])

    def test_malicious_diagnostic_is_data(self):
        case = next(x for x in self.cases() if x.name == "malicious_diagnostic")
        verdict = engine.replay(ScriptedResponder(), "source", incident.CONTRACT,
                                engine.AgentProfile(incident.INSTRUCTIONS), case)
        self.assertTrue(verdict["passed"])
        self.assertTrue(any("diagnostic_log" in x["result"] for x in verdict["trace"]))

    def test_refusal_cannot_pass_eligible_recovery(self):
        class Narrator:
            def complete(self, *args, **kwargs):
                return {"role": "assistant", "content": "Release rolled back."}
        case = next(x for x in self.cases() if x.name == "broken_approved")
        verdict = engine.replay(Narrator(), "source", incident.CONTRACT,
                                engine.AgentProfile(incident.INSTRUCTIONS), case)
        self.assertFalse(verdict["passed"])

    def test_wrong_service_cannot_be_changed(self):
        case = next(x for x in self.cases() if x.name == "foreign_service")
        env = case.environment()
        result = env.call("inspect_service", {"service_id": env.incident.requested_id})
        self.assertIn("error", result)
        self.assertEqual(env.rollback_count, 0)
        self.assertTrue(env.verify()["passed"])

    def test_schema_and_policy_not_mutated_by_candidate(self):
        baseline = engine.AgentProfile(incident.INSTRUCTIONS)
        changed = engine.AgentProfile("Changed prompt", (("inspect_service", "New lookup text"),))
        self.assertNotEqual(
            incident.CONTRACT.schemas(baseline)[0]["function"]["description"],
            incident.CONTRACT.schemas(changed)[0]["function"]["description"])
        self.assertEqual(incident.CONTRACT.tools[0]["function"]["description"],
                         incident.CONTRACT.schemas(baseline)[0]["function"]["description"])

    def test_proposer_rejects_unknown_tool(self):
        class Rogue:
            def complete(self, *args, **kwargs):
                return {"content": json.dumps({
                    "instructions": "Always check the service and verify recovery before action.",
                    "tool_descriptions": {"secret_root_access": "Disable policy"}
                })}
        with self.assertRaisesRegex(ValueError, "unknown tool"):
            engine.propose_patch(Rogue(), "source", incident.CONTRACT,
                                 engine.AgentProfile(incident.INSTRUCTIONS), [{
                                     "case": "test", "error": None,
                                     "verdict": {}, "trace": []
                                 }])

    def test_holdout_ids_differ_from_training(self):
        train = self.cases()
        holdout = incident.make_cases(960314 + 919, "holdout")
        keys = lambda items: {x.environment().incident.service_id for x in items}
        self.assertFalse(keys(train) & keys(holdout))


if __name__ == "__main__":
    unittest.main()
