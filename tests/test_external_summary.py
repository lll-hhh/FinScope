from __future__ import annotations

import unittest

from benchmarks.serve_privacy_proxy import stockbench_catalog
from benchmarks.summarize_external_matrix import (
    catalog_privacy_attack,
    decision_preservation_from_audits,
    percentile,
    reference_continuity_from_audits,
)


class ExternalSummaryTests(unittest.TestCase):
    def test_percentile_uses_observed_nearest_rank(self):
        self.assertEqual(percentile([1, 2, 3, 4], 0.95), 4.0)
        self.assertIsNone(percentile([], 0.95))

    def test_catalog_attack_respects_alias_lifecycle(self):
        entries = stockbench_catalog()
        global_alias = catalog_privacy_attack(entries, "global_alias")
        episode_alias = catalog_privacy_attack(entries, "episode_alias")
        self.assertEqual(global_alias["reid_at_1"], 1 / len(entries))
        self.assertEqual(global_alias["link_auc"], 1.0)
        self.assertEqual(episode_alias["reid_at_1"], 1 / len(entries))
        self.assertEqual(episode_alias["link_auc"], 0.5)

    def test_vanilla_is_fully_identifying(self):
        result = catalog_privacy_attack(stockbench_catalog(), "vanilla")
        self.assertEqual(result["reid_at_1"], 1.0)
        self.assertEqual(result["link_auc"], 1.0)

    def test_external_audit_closed_loop_metrics(self):
        vanilla = [
            {
                "status": "ok",
                "episode_id": "day-1",
                "role": "research",
                "input_fingerprint": "input-1",
                "decision_fingerprint": "decision-a",
            }
        ]
        protected = [
            {
                **vanilla[0],
                "bindings": [
                    {"canonical_id": "AAPL", "alias": "EA_ASSET_1"}
                ],
            },
            {
                "status": "ok",
                "episode_id": "day-1",
                "role": "trade",
                "input_fingerprint": "input-2",
                "decision_fingerprint": "decision-b",
                "bindings": [
                    {"canonical_id": "AAPL", "alias": "EA_ASSET_1"}
                ],
            },
        ]
        decision = decision_preservation_from_audits(protected[:1], vanilla)
        continuity = reference_continuity_from_audits(protected)
        self.assertEqual(decision["rate"], 1.0)
        self.assertEqual(continuity["episode_rate"], 1.0)
        self.assertEqual(continuity["asset_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
