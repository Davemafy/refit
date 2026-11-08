"""Operator-owned Vultr model catalog: configurable without untrusted model selection."""
import unittest
from unittest.mock import patch

from scripts.application_run import DEFAULT_MODELS, configured_models


class ModelCatalogTests(unittest.TestCase):
    def test_default_remains_evidence_backed(self):
        with patch.dict("os.environ", {"REFIT_APPLICATION_MODELS": ""}):
            self.assertEqual(configured_models(), DEFAULT_MODELS)

    def test_operator_can_add_a_model_without_disabling_baseline(self):
        available = configured_models("deepseek-v4.1-flash-1017,glm-5.2,experimental-model-3")
        self.assertEqual(available[:2], DEFAULT_MODELS)
        self.assertIn("experimental-model-3", available)

    def test_rejects_duplicate_untrusted_and_invalid_catalogs(self):
        for malformed in ("only-one-model", "a,a", "a, model with spaces",
                          "a,../../private", "a,model\nname",
                          ",".join(f"m{i}" for i in range(13))):
            with self.subTest(value=malformed):
                with self.assertRaises(ValueError):
                    configured_models(malformed)


if __name__ == "__main__":
    unittest.main()
