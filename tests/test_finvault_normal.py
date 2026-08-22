from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.run_finvault_normal import load_cases


class FinVaultNormalRunnerTests(unittest.TestCase):
    def test_load_cases_adapts_normal_query_to_attack_runner_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "sandbox" / "normal_datasets"
            dataset.mkdir(parents=True)
            (dataset / "scenario_00_normal.json").write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "id": "normal-1",
                                "query_prompt": "Process CUSTOMER-000001",
                                "related_vulnerability": "V1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            cases = load_cases(root, "00")

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["attack_prompt"], "Process CUSTOMER-000001")
        self.assertEqual(cases[0]["all_turns"], ["Process CUSTOMER-000001"])
        self.assertEqual(cases[0]["target_vulnerability"], "V1")
        self.assertEqual(cases[0]["attack_type"], "normal")


if __name__ == "__main__":
    unittest.main()
