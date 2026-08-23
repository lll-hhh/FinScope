from __future__ import annotations

import unittest

from benchmarks.closed_loop_metrics import (
    decision_preservation,
    exact_action_restore,
    reference_continuity,
)


class ClosedLoopMetricTests(unittest.TestCase):
    def test_decision_preservation_uses_all_aligned_episodes(self) -> None:
        baseline = [
            {"episode_id": "d1", "valid": True, "action": {"asset": "A", "action": "buy"}},
            {"episode_id": "d2", "valid": True, "action": {"asset": "B", "action": "sell"}},
            {"episode_id": "d3", "valid": True, "action": {"asset": "C", "action": "hold"}},
        ]
        protected = [
            {"episode_id": "d1", "valid": True, "action": {"asset": "A", "side": "buy"}},
            {"episode_id": "d2", "valid": False, "action": None},
            {"episode_id": "d3", "valid": True, "action": {"asset": "C", "action": "hold"}},
        ]
        metric = decision_preservation(protected, baseline)
        self.assertEqual(metric["preserved"], 2)
        self.assertEqual(metric["episodes"], 3)
        self.assertAlmostEqual(metric["rate"], 2 / 3)

    def test_reference_continuity_requires_repeated_views(self) -> None:
        stable = reference_continuity(
            {
                "research": {"A": "FS_ASSET_1"},
                "risk": {"A": "FS_ASSET_1"},
                "trade": {"A": "FS_ASSET_1"},
            }
        )
        broken = reference_continuity(
            {
                "research": {"A": "FS_ASSET_1"},
                "risk": {"A": "FS_ASSET_2"},
                "trade": {"A": "FS_ASSET_1"},
            }
        )
        uncovered = reference_continuity({"research": {"A": "FS_ASSET_1"}})
        self.assertEqual(stable["rate"], 1.0)
        self.assertEqual(broken["rate"], 0.0)
        self.assertIsNone(uncovered["rate"])

    def test_exact_restore_includes_numeric_fields_and_execution(self) -> None:
        resolver = {"FS_ASSET_1": "AAPL"}
        outbound = {"asset": "FS_ASSET_1", "action": "buy", "amount": 1000}
        restored = {"asset": "AAPL", "action": "buy", "amount": 1000.0}
        self.assertTrue(
            exact_action_restore(outbound, restored, resolver, executed=True)
        )
        self.assertFalse(
            exact_action_restore(
                outbound,
                {"asset": "AAPL", "action": "buy", "amount": 900.0},
                resolver,
                executed=True,
            )
        )
        self.assertFalse(
            exact_action_restore(outbound, restored, resolver, executed=False)
        )


if __name__ == "__main__":
    unittest.main()

