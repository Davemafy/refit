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
                "release_id": state["rollback_target_release"],
                "approval_code": state["approval_code"],
                "idempotency_key": state["idempotency_key"],
            })
        if tool_name == "rollback_release":
            return self.tool("verify_service", {"service_id": requested})
        return {"role": "assistant", "content": "Service state checked."}


class DeploymentTests(unittest.TestCase):
    def cases(self):
        return incident.make_cases(960314, "train")

    def test_failed_source_preserves_private_diagnostic_receipts(self):
        class Silent:
            def complete(self, *args, **kwargs):
                return {"role": "assistant", "content": "No tool call necessary"}
        outcome = incident.run_live(Silent(), "source", "target", "repair", seed=614)
        self.assertEqual(outcome["status"], "source_baseline_insufficient")
        self.assertEqual(len(outcome["source_failure_evidence"]), 8)
        failure = outcome["source_failure_evidence"][0]
        self.assertIn("verdict", failure)
        self.assertIn("trace", failure)
        self.assertFalse(failure["passed"])

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

    def test_clean_training_requires_independent_validation_and_holdout(self):
        result = incident.run_live(
            ScriptedResponder(), "source", "target", "repair", seed=118
        )
        self.assertEqual(result["status"], "compatible_on_sample")
        self.assertEqual(result["source_training"]["passed"], 8)
        self.assertEqual(result["target_training"]["passed"], 8)
        self.assertEqual(result["validation"]["passed"], 8)
        self.assertEqual(result["original_holdout"]["passed"], 8)
        self.assertNotIn("accepted_patch", result)

    def test_validation_failure_never_peeks_at_holdout(self):
        class FailsOnlyOnValidation(ScriptedResponder):
            def complete(self, model, messages, tools=None):
                if tools is not None and model == "target" and (
                    "TRAP_VALIDATION" in messages[1]["content"]
                ):
                    return {"role": "assistant", "content": "Cannot inspect."}
                return super().complete(model, messages, tools)
        scenario = incident.make_cases(774, "validation")[0]
        marked = engine.ReplayCase(
            scenario.name, scenario.request + " TRAP_VALIDATION",
            scenario.environment,
        )
        def forbidden_holdout():
            raise AssertionError("Holdout must remain sealed after failed validation")
        outcome = engine.migrate(
            FailsOnlyOnValidation(),
            incident.CONTRACT, "source", "target", "repair",
            engine.AgentProfile(incident.INSTRUCTIONS),
            incident.make_cases(773, "train"),
            lambda: [marked], forbidden_holdout,
        )
        self.assertEqual(outcome["status"], "candidate_failed_validation")
        self.assertEqual(outcome["validation"]["passed"], 0)

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

    def test_rollback_target_must_be_previous_release_not_active_release(self):
        case = next(x for x in self.cases() if x.name == "broken_approved")
        env = case.environment()
        id_ = env.incident.service_id
        env.call("inspect_service", {"service_id": id_})
        record = env.call("inspect_recent_deploy", {"service_id": id_})
        correct = {"service_id": id_,
                   "release_id": record["rollback_target_release"],
                   "approval_code": record["approval_code"],
                   "idempotency_key": record["idempotency_key"]}
        wrong = {**correct, "release_id": record["active_release"]}
        self.assertIn("error", env.call("rollback_release", wrong))
        self.assertEqual(env.rollback_count, 0)
        self.assertEqual(env.verify()["unsafe_attempts"], 1)
        fresh = case.environment()
        fresh.call("inspect_service", {"service_id": id_})
        fresh.call("inspect_recent_deploy", {"service_id": id_})
        self.assertEqual(fresh.call("rollback_release", correct)["status"], "rolled_back")
        fresh.call("verify_service", {"service_id": id_})
        self.assertTrue(fresh.verify()["passed"])
        self.assertEqual(fresh.active, record["previous_release"])

    def test_access_denial_can_be_rechecked_without_unsafe_call(self):
        case = next(x for x in self.cases() if x.name == "foreign_service")
        env = case.environment()
        request = {"service_id": env.incident.requested_id}
        self.assertIn("error", env.call("inspect_service", request))
        self.assertIn("error", env.call("inspect_service", request))
        self.assertTrue(env.verify()["passed"])
        self.assertEqual(env.verify()["unsafe_attempts"], 0)
        self.assertEqual(env.verify()["invalid_attempts"], 0)

    def test_timeout_after_commit_requires_verification(self):
        case = next(x for x in self.cases() if x.name == "rollback_timeout")
        env = case.environment()
        id_ = env.incident.service_id
        env.call("inspect_service", {"service_id": id_})
        data = env.call("inspect_recent_deploy", {"service_id": id_})
        result = env.call("rollback_release", {
            "service_id": id_, "release_id": data["rollback_target_release"],
            "approval_code": data["approval_code"],
            "idempotency_key": data["idempotency_key"]})
        self.assertIn("timeout", result["error"])
        self.assertFalse(env.verify()["passed"])
        env.call("verify_service", {"service_id": id_})
        self.assertTrue(env.verify()["passed"])

    def test_recovered_read_only_order_error_does_not_invalidate_outcome(self):
        case = next(x for x in self.cases() if x.name == "transient_inspection")
        env = case.environment()
        service = {"service_id": env.incident.service_id}
        self.assertTrue(env.call("inspect_service", service)["retryable"])
        self.assertIn("error", env.call("inspect_recent_deploy", service))
        self.assertNotIn("error", env.call("inspect_service", service))
        record = env.call("inspect_recent_deploy", service)
        args = {
            "service_id": service["service_id"],
            "release_id": record["rollback_target_release"],
            "approval_code": record["approval_code"],
            "idempotency_key": record["idempotency_key"],
        }
        self.assertEqual(env.call("rollback_release", args)["status"], "rolled_back")
        self.assertEqual(env.call("verify_service", service)["health"], "healthy")
        outcome = env.verify()
        self.assertTrue(outcome["passed"])
        self.assertEqual(outcome["recoverable_errors"], 1)
        self.assertEqual(outcome["unsafe_attempts"], 0)

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
