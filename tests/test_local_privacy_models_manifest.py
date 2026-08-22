from __future__ import annotations

import json
from pathlib import Path
import unittest


class LocalPrivacyModelManifestTests(unittest.TestCase):
    def test_manifest_has_ten_instruction_models_under_four_billion(self) -> None:
        path = Path(__file__).parents[1] / "benchmarks" / "local_privacy_models.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        models = payload["models"]

        self.assertEqual(len(models), 10)
        self.assertEqual(len({item["model_id"] for item in models}), 10)
        self.assertLessEqual(payload["max_parameters_b"], 4.0)
        self.assertTrue(all(item["parameters_b"] <= 4.0 for item in models))
        self.assertTrue(all(item["instruction_tuned"] for item in models))
        self.assertIn("google/gemma-4-4b-it", {item["model_id"] for item in models})
        self.assertNotIn("microsoft/Phi-4-mini-instruct", {item["model_id"] for item in models})
        self.assertEqual(
            {item["availability"] for item in models},
            {"ready", "download_required", "alias_required"},
        )
        self.assertEqual(models[-1]["availability"], "alias_required")


if __name__ == "__main__":
    unittest.main()
