from __future__ import annotations

import unittest

from benchmarks.finalize_qwen_external_matrix import row_text


class ExternalFinalizerTests(unittest.TestCase):
    def test_formats_stockbench_row(self):
        row = {
            "benchmark": "stockbench",
            "method": "global_alias",
            "native": {
                "total_return": 0.04,
                "sortino_annual": 2.0,
                "max_drawdown": 0.03,
                "sharpe": 1.5,
            },
            "privacy": {"reid_at_1": 0.05, "link_auc": 1.0},
            "audit": {
                "exact_action_restore_rate": 1.0,
                "e2e_p95_ms": 2500,
            },
            "decision_preservation": {"rate": 0.9},
            "reference_continuity": {"episode_rate": 1.0},
            "token_delta_vs_vanilla": 0.1,
        }
        value = row_text(row)
        self.assertIn("| StockBench | Qwen3.8-27B | Global Alias |", value)
        self.assertIn("| 90.00% | 100.00% | 100.00% | 5.00% | 1.000 | +10.0% | 2.500 s |", value)


if __name__ == "__main__":
    unittest.main()
