from __future__ import annotations

import json
import unittest

from benchmarks.run_nlpcc_real import (
    FUND_POOL,
    LocalPrivacyAgent,
    asset_catalog,
    prepare_outbound,
    restore_and_validate,
)


def payload() -> dict:
    return {
        "date": "2025-01-02",
        "candidate_pool": [
            {"asset": asset, "name": profile["name"], "prices": []}
            for asset, profile in zip(
                FUND_POOL,
                [
                    {"name": entry["name"]}
                    for entry in asset_catalog()
                ],
            )
        ],
        "news": [],
        "portfolio": {"cash": 100000.0, "holdings": [], "total_value": 100000.0},
    }


class RealNlpccRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = LocalPrivacyAgent(asset_catalog(), default_level="P3")
        self.fixed = {
            asset: "FIXED_ASSET_%03d" % index
            for index, asset in enumerate(FUND_POOL, start=1)
        }

    def test_p3_payload_round_trips_through_audited_action(self) -> None:
        outbound, scope, representations, _ = prepare_outbound(
            "finscope", payload(), 20250102, self.agent, self.fixed, "P3"
        )
        self.assertIsNotNone(scope)
        serialized = json.dumps(outbound, ensure_ascii=False)
        for entry in asset_catalog():
            self.assertNotIn(entry["canonical_id"], serialized)
            self.assertNotIn(entry["name"], serialized)
        self.assertIn("<fin-ref", serialized)

        action = {
            "asset": outbound["candidate_pool"][0]["asset"],
            "action": "buy",
            "amount": 1000.0,
        }
        restored, valid, rejection = restore_and_validate(
            "finscope", action, scope, self.agent, {value: key for key, value in self.fixed.items()}
        )
        self.assertTrue(valid, rejection)
        self.assertEqual(restored["asset"], FUND_POOL[0])
        self.assertEqual(representations[FUND_POOL[0]], action["asset"])
        self.agent.close_scope(scope)

    def test_handles_rotate_across_days(self) -> None:
        first, first_scope, _, _ = prepare_outbound(
            "finscope", payload(), 20250102, self.agent, self.fixed, "P3"
        )
        self.agent.close_scope(first_scope)
        second, second_scope, _, _ = prepare_outbound(
            "finscope", payload(), 20250103, self.agent, self.fixed, "P3"
        )
        self.assertNotEqual(
            first["candidate_pool"][0]["asset"],
            second["candidate_pool"][0]["asset"],
        )
        self.agent.close_scope(second_scope)


if __name__ == "__main__":
    unittest.main()
