"""Both agent domains use one migration engine and its protected verifiers."""
import json
import re
import unittest

from scripts import migration_engine, refund_adapter, deployment_incident_probe, refit_cli


class SyntheticRefundResponder:
    def complete(self, model, messages, tools=None):
        if tools is None:
            old = json.loads(messages[-1]["content"])["existing_configuration"]
            return {"role": "assistant", "content": json.dumps({
                "instructions": old["instructions"] + " Preserve exact minor-unit amounts and look up before refunding.",
                "tool_descriptions": {"issue_refund": (
                    "Issue the authorized exact integer minor-unit refund with the "
                    "trusted idempotency_key, after get_order has confirmed eligibility."
                )},
            })}
        original = messages[1]["content"]
        order = re.search(r"ORD-\d+", original).group(0)
        last = next((m for m in reversed(messages) if m["role"] == "tool"), None)
        if last is None:
            return self._call("get_order", {"order_id": order})
        state = json.loads(last["content"])
        if state.get("retryable") or "timeout AFTER" in state.get("error", ""):
            return self._call("get_order", {"order_id": order})
        if "requester_id" not in state:
            return {"role": "assistant", "content": "No change."}
        if (state["requester_id"] != state["owner_id"] or
                not state["refundable"] or state["refunded"]):
            return {"role": "assistant", "content": "No permitted refund."}
        return self._call("issue_refund", {
            "order_id": order,
            "amount_minor_units": state["amount_minor_units"],
            "idempotency_key": state["idempotency_key"],
        })

    @staticmethod
    def _call(name, arguments):
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "test-call", "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments),
            },
        }]}


class AdapterContractTests(unittest.TestCase):
    def test_both_adapters_have_distinct_tools_but_common_interface(self):
        self.assertIsNot(refund_adapter.CONTRACT, deployment_incident_probe.CONTRACT)
        self.assertEqual(refund_adapter.CONTRACT.tool_names(), {"get_order", "issue_refund"})
        self.assertEqual(deployment_incident_probe.CONTRACT.tool_names(), {
            "inspect_service", "inspect_recent_deploy", "rollback_release", "verify_service",
        })
        for module in (refund_adapter, deployment_incident_probe):
            self.assertTrue(callable(module.run_live))
            self.assertEqual(len(module.make_cases(991, "train")), 8)

    def test_generic_refund_evaluator_preserves_timeout_recheck_rule(self):
        suite = refund_adapter.make_cases(9221, "train")
        evaluation = migration_engine.evaluate(
            SyntheticRefundResponder(), "source",
            refund_adapter.CONTRACT,
            migration_engine.AgentProfile(refund_adapter.PROMPT), suite)
        self.assertEqual(evaluation["passed"], 8, evaluation["cases"])
        self.assertEqual(evaluation["unsafe_attempts"], 0)

    def test_generic_refund_migration_succeeds_without_fake_repair(self):
        result = refund_adapter.run_live(
            SyntheticRefundResponder(), "source", "target", "repair", 911)
        self.assertEqual(result["status"], "compatible_on_sample")
        self.assertEqual(result["validation"]["passed"], 8)
        self.assertEqual(result["original_holdout"]["passed"], 8)
        self.assertNotIn("accepted_patch", result)

    def test_false_refund_claim_fails_independent_state_oracle(self):
        class Narrator:
            def complete(self, *args, **kwargs):
                return {"role": "assistant", "content": "Refund succeeded."}
        case = next(x for x in refund_adapter.make_cases(991, "train")
                    if x.name == "eligible")
        verdict = migration_engine.replay(
            Narrator(), "source", refund_adapter.CONTRACT,
            migration_engine.AgentProfile(refund_adapter.PROMPT), case)
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["verdict"]["successful_lookup"])

    def test_cli_resolves_only_valid_trusted_module_paths(self):
        self.assertIs(refit_cli.resolve_adapter("refund", None), refund_adapter)
        self.assertIs(refit_cli.resolve_adapter("deployment", None),
                      deployment_incident_probe)
        with self.assertRaisesRegex(ValueError, "invalid Python"):
            refit_cli.resolve_adapter("refund", "os;rm -rf /")


if __name__ == "__main__":
    unittest.main()
