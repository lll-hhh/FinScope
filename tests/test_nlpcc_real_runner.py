from __future__ import annotations

import json
import re
import unittest

from benchmarks.run_nlpcc_real import (
    BackendResult,
    FUND_POOL,
    LocalPrivacyAgent,
    asset_catalog,
    build_episode_aliases,
    coarsen_market_features,
    prepare_outbound,
    rewrite_news,
    restore_and_validate,
)
from benchmarks.merge_nlpcc_runs import compute_expanded_metrics
from benchmarks.run_nlpcc_fault_injection import perturbations
from benchmarks.run_nlpcc_privacy_attacks import (
    candidate_signature,
    moving_block_interval,
    roc_auc,
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
        expected_asset = next(
            asset for asset, representation in representations.items()
            if representation == action["asset"]
        )
        self.assertEqual(restored["asset"], expected_asset)
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

    def test_episode_aliases_are_stable_within_day_and_rotate_across_days(self) -> None:
        first = build_episode_aliases(20250102)
        repeated = build_episode_aliases(20250102)
        second = build_episode_aliases(20250103)

        self.assertEqual(first, repeated)
        self.assertEqual(set(first), set(FUND_POOL))
        self.assertTrue(all(first[asset] != second[asset] for asset in FUND_POOL))
        self.assertEqual(len(set(first.values())), len(FUND_POOL))

    def test_llm_rewrite_replaces_titles_and_records_usage(self) -> None:
        class FakeBackend:
            def generate(self, prompt, *, max_new_tokens=None):
                self.prompt = prompt
                self.limit = max_new_tokens
                return BackendResult(
                    '{"news":["贵金属避险需求上升","科技行业承压"]}',
                    101,
                    22,
                    12.5,
                )

        backend = FakeBackend()
        outbound = {
            "news": [
                {"source": "a", "title": "黄金ETF上涨"},
                {"source": "b", "title": "科创50回落"},
            ]
        }
        rewritten, usage, succeeded = rewrite_news(backend, outbound)

        self.assertTrue(succeeded)
        self.assertEqual(backend.limit, 384)
        self.assertEqual(usage.input_tokens, 101)
        self.assertEqual(
            [item["title"] for item in rewritten["news"]],
            ["贵金属避险需求上升", "科技行业承压"],
        )

    def test_market_features_remove_exact_price_fingerprints(self) -> None:
        raw = payload()
        raw["candidate_pool"][0]["prices"] = [
            {"date": "2025-01-01", "open": 101.23, "close": 102.34, "pct_change": 1.2345},
            {"date": "2025-01-02", "open": 103.45, "close": None, "pct_change": None},
        ]

        for level in ("P1", "P2", "P3", "P4", "P5"):
            protected = coarsen_market_features(raw, level)
            serialized = json.dumps(protected, ensure_ascii=False)
            self.assertNotIn("101.23", serialized)
            self.assertNotIn("102.34", serialized)
            self.assertNotIn("103.45", serialized)
            self.assertNotIn("1.2345", serialized)
            self.assertNotIn("2025-01-01", serialized)
            self.assertNotIn("prices", protected["candidate_pool"][0])
        self.assertEqual(
            coarsen_market_features(raw, "P5")["candidate_pool"][0]["market_features"],
            {},
        )

    def test_disclosed_static_signatures_have_no_singleton_assets(self) -> None:
        handle = re.compile(r'id="[^"]+"')
        for level in ("P1", "P2", "P3", "P4", "P5"):
            outbound, scope, _, _ = prepare_outbound(
                "finscope", payload(), 20250102, self.agent, self.fixed, level
            )
            signatures = []
            for candidate in outbound["candidate_pool"]:
                static = {
                    key: value
                    for key, value in candidate.items()
                    if key != "market_features"
                }
                static["asset"] = handle.sub('id="HANDLE"', static["asset"])
                static["name"] = handle.sub('id="HANDLE"', static["name"])
                signatures.append(
                    json.dumps(static, ensure_ascii=False, sort_keys=True)
                )
            for signature in set(signatures):
                self.assertGreaterEqual(signatures.count(signature), 2, (level, signature))
            self.agent.close_scope(scope)

    def test_finscope_randomizes_candidate_position_with_scope_handles(self) -> None:
        outbound, scope, representations, _ = prepare_outbound(
            "finscope", payload(), 20250102, self.agent, self.fixed, "P5"
        )
        observed = [item["asset"] for item in outbound["candidate_pool"]]
        self.assertEqual(observed, sorted(observed))
        self.assertEqual(set(observed), set(representations.values()))
        self.agent.close_scope(scope)

    def test_expanded_metrics_include_rewrite_call_cost(self) -> None:
        records = []
        summaries = {}
        histories = {}
        for method in (
            "vanilla",
            "deletion",
            "llm_rewrite",
            "fixed_alias",
            "episode_alias",
            "finscope",
        ):
            records.append(
                {
                    "date": 20250102,
                    "method": method,
                    "parsed": True,
                    "valid": True,
                    "executed": True,
                    "rejection_reason": None,
                    "restored_action": {"asset": FUND_POOL[0], "action": "buy"},
                    "direct_identifier_leak": False,
                    "preprocess_ms": 1.0,
                    "postprocess_ms": 2.0,
                    "model_latency_ms": 10.0,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "rewrite_input_tokens": 50 if method == "llm_rewrite" else 0,
                    "rewrite_output_tokens": 10 if method == "llm_rewrite" else 0,
                    "rewrite_latency_ms": 5.0 if method == "llm_rewrite" else 0.0,
                    "rewrite_succeeded": True if method == "llm_rewrite" else None,
                    "cash": 50_000.0,
                }
            )
            summaries[method] = {
                "max_drawdown": 0.01,
                "direct_identifier_leak_rate": 0.0,
                "cross_day_unique_link_rate": 0.0,
            }
            histories[method] = [100_000.0, 101_000.0]

        metrics = compute_expanded_metrics(records, histories, summaries)["by_method"]
        rewrite = metrics["llm_rewrite"]["cost"]
        self.assertEqual(rewrite["total_input_tokens"], 150)
        self.assertEqual(rewrite["total_output_tokens"], 30)
        self.assertEqual(rewrite["average_model_latency_ms"], 15.0)
        self.assertEqual(rewrite["average_e2e_latency_ms"], 18.0)
        self.assertEqual(rewrite["rewrite_success_rate"], 1.0)

    def test_attack_metrics_handle_ties_and_exclude_identity_fields(self) -> None:
        self.assertEqual(roc_auc([1.0, 1.0], [0.0, 0.0]), 1.0)
        self.assertEqual(roc_auc([0.5, 0.5], [0.5, 0.5]), 0.5)
        self.assertEqual(moving_block_interval([0.25] * 20, 100, 5), (0.25, 0.25))
        first = {"asset": "SECRET_A", "name": "Secret A", "category": "group"}
        second = {"asset": "SECRET_B", "name": "Secret B", "category": "group"}
        self.assertEqual(candidate_signature(first), candidate_signature(second))

    def test_fault_injection_covers_execution_and_binding_failures(self) -> None:
        representations = {
            asset: f'<fin-ref type="asset" id="FS_ASSET_{index:08X}">金融资产</fin-ref>'
            for index, asset in enumerate(FUND_POOL, 1)
        }
        variants = perturbations(
            {},
            representations,
            representations,
            {"asset": FUND_POOL[0], "action": "buy", "amount": 1000.0},
        )
        self.assertTrue(
            {
                "descriptor_without_handle",
                "binding_descriptor_tamper",
                "same_type_handle_swap",
                "stale_previous_day_handle",
                "malformed_json",
                "numeric_out_of_range",
                "execution_cash_violation",
            }.issubset(variants)
        )


if __name__ == "__main__":
    unittest.main()
