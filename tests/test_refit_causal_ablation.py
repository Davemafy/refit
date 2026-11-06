"""Ablation config and evaluation-boundary tests; these make no paid API calls."""
import unittest
from unittest.mock import patch
from scripts import refit_causal_ablation as ablation


class CausalAblationTests(unittest.TestCase):
    def test_pre_registered_four_conditions(self):
        conditions = dict(ablation.conditions())
        self.assertEqual(set(conditions), {"baseline", "guard_only", "instructions_only", "combined"})
        self.assertFalse(conditions["baseline"].force_initial_lookup)
        self.assertTrue(conditions["guard_only"].force_initial_lookup)
        self.assertFalse(conditions["instructions_only"].force_initial_lookup)
        self.assertTrue(conditions["combined"].force_initial_lookup)
        self.assertEqual(conditions["baseline"].instructions, conditions["guard_only"].instructions)
        self.assertEqual(conditions["instructions_only"].instructions, conditions["combined"].instructions)
        self.assertNotEqual(conditions["baseline"].instructions, conditions["instructions_only"].instructions)

    def test_fresh_state_shared_across_all_four_conditions(self):
        calls = []
        def fake_evaluate(client, model, config, scenarios):
            calls.append((config, tuple((x.case.order_id, x.case.amount_minor) for x in scenarios)))
            return {"passed": 8, "total": 8, "unsafe_attempts": 0, "cases": []}
        class Fake:
            max_requests = 160
            requests = 0
        with patch.object(ablation, "evaluate_stress", side_effect=fake_evaluate):
            result = ablation.run_ablation(Fake(), "target", seed=96342)
        self.assertEqual(result["status"], "diagnostic_ablation_not_generalization")
        self.assertEqual([x["condition"] for x in result["conditions"]], [
            "baseline", "guard_only", "instructions_only", "combined"])
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(set(x[1] for x in calls)), 1)
        self.assertEqual(len(set(y[0] for y in calls[0][1])), 8)

    def test_fails_closed_when_budget_spent(self):
        class Fake:
            max_requests = 1
            requests = 1
        with patch.object(ablation, "evaluate_stress") as f:
            result = ablation.run_ablation(Fake(), "target", seed=111)
        self.assertEqual(result["status"], "incomplete_request_budget")
        self.assertFalse(result["conditions"])
        f.assert_not_called()


if __name__ == "__main__":
    unittest.main()
