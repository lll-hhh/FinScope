from __future__ import annotations

import unittest

from finscope import ActionValidationError, FinScopeMediator, ScopeNotFoundError


CATALOG = [
    {"name": "Apple Inc.", "aliases": ["AAPL"]},
    {"name": "Microsoft Corporation", "aliases": ["MSFT"]},
]


class FinScopeTests(unittest.TestCase):
    def test_task_scope_keeps_aliases_consistent_across_agents(self) -> None:
        mediator = FinScopeMediator(CATALOG)
        scope = mediator.open_scope("rebalance-42", "2026-08-14")

        research = mediator.sanitize_prompt("研究 AAPL 和 Apple Inc. 的新闻", scope)
        risk = mediator.sanitize_prompt("风险检查 Apple Inc.，现有候选池包含 AAPL", scope)

        self.assertNotIn("AAPL", research)
        self.assertNotIn("Apple Inc.", research)
        self.assertEqual(research.count("FS_ASSET_"), 2)
        self.assertEqual(risk.count("FS_ASSET_"), 2)
        self.assertEqual(
            mediator.get_alias("AAPL", scope),
            mediator.get_alias("Apple Inc.", scope),
        )

    def test_new_trading_day_rotates_aliases_and_closes_old_scope(self) -> None:
        mediator = FinScopeMediator(["Tesla"])
        day_one = mediator.open_scope("daily-task", "2026-08-14")
        alias_one = mediator.get_alias("Tesla", day_one)
        day_two = mediator.open_scope("daily-task", "2026-08-15")
        alias_two = mediator.get_alias("Tesla", day_two)

        self.assertNotEqual(day_one.id, day_two.id)
        self.assertNotEqual(alias_one, alias_two)
        with self.assertRaises(ScopeNotFoundError):
            mediator.restore_output(alias_one, day_one)

    def test_nested_tool_result_round_trips_to_canonical_assets(self) -> None:
        mediator = FinScopeMediator(CATALOG)
        scope = mediator.open_scope("tool-task", "2026-08-14")
        raw = {
            "candidate_pool": ["AAPL", "MSFT"],
            "holdings": [{"symbol": "AAPL", "weight": 0.25}],
            "news": "Apple Inc. announced a new product.",
        }

        sanitized = mediator.sanitize_tool_result(raw, scope)
        self.assertEqual(sanitized["holdings"][0]["weight"], 0.25)
        self.assertNotIn("AAPL", repr(sanitized))
        self.assertNotIn("Apple Inc.", repr(sanitized))
        self.assertEqual(
            mediator.restore_output(sanitized, scope),
            {
                "candidate_pool": ["Apple Inc.", "Microsoft Corporation"],
                "holdings": [{"symbol": "Apple Inc.", "weight": 0.25}],
                "news": "Apple Inc. announced a new product.",
            },
        )

    def test_external_call_restores_response_and_validates_action(self) -> None:
        mediator = FinScopeMediator(CATALOG)
        scope = mediator.open_scope("order-task", "2026-08-14")
        alias = mediator.get_alias("AAPL", scope)

        def fake_external(payload):
            self.assertIn(alias, payload["prompt"])
            self.assertNotIn("AAPL", payload["prompt"])
            return {"asset": alias, "side": "buy", "quantity": 10}

        restored = mediator.call_external({"prompt": "分析 AAPL"}, fake_external, scope)
        result = mediator.validate_action(restored, scope)
        self.assertEqual(
            result.action,
            {"asset": "Apple Inc.", "side": "buy", "quantity": 10},
        )

    def test_unknown_alias_and_invalid_actions_are_rejected(self) -> None:
        mediator = FinScopeMediator(CATALOG)
        scope = mediator.open_scope("bad-order", "2026-08-14")

        with self.assertRaisesRegex(ActionValidationError, "unknown asset alias"):
            mediator.validate_action(
                {"asset": "FS_ASSET_AAAAAAAA", "side": "buy", "quantity": 1}, scope
            )
        with self.assertRaisesRegex(ActionValidationError, "unsupported order side"):
            mediator.validate_action({"asset": "AAPL", "side": "borrow"}, scope)
        with self.assertRaisesRegex(ActionValidationError, "decimal fraction"):
            mediator.validate_action({"asset": "AAPL", "side": "buy", "weight": 2}, scope)
        with self.assertRaisesRegex(
            ActionValidationError, "both an asset and an order side"
        ):
            mediator.validate_action({"asset": "AAPL"}, scope)

    def test_cjk_asset_names_and_symbol_keyed_holdings_are_sanitized(self) -> None:
        mediator = FinScopeMediator([{"name": "贵州茅台", "aliases": ["600519"]}])
        scope = mediator.open_scope("cn-portfolio", "2026-08-14")

        prompt = mediator.sanitize_prompt("请分析贵州茅台的风险", scope)
        holdings = mediator.sanitize_tool_result({"holdings": {"600519": 0.4}}, scope)

        self.assertNotIn("贵州茅台", prompt)
        self.assertIn("FS_ASSET_", prompt)
        self.assertNotIn("600519", repr(holdings))
        self.assertEqual(
            mediator.restore_output(holdings, scope),
            {"holdings": {"贵州茅台": 0.4}},
        )

    def test_numeric_cjk_name_is_sanitized_before_financial_suffix(self) -> None:
        mediator = FinScopeMediator(
            [
                {"name": "沪深300", "aliases": ["000300"]},
                {"name": "黄金", "aliases": ["GOLD"]},
            ]
        )
        scope = mediator.open_scope("cn-financial-suffix", "2026-08-14")

        sanitized = mediator.sanitize_prompt(
            "汇金增持沪深300ETF，并关注黄金ETF基金", scope
        )

        self.assertNotIn("沪深300", sanitized)
        self.assertNotIn("黄金", sanitized)
        self.assertEqual(sanitized.count("FS_ASSET_"), 2)
        self.assertIn("ETF", sanitized)

    def test_task_scope_context_erases_mapping(self) -> None:
        mediator = FinScopeMediator(["AAPL"])
        with mediator.task_scope("context-task", "2026-08-14") as scope:
            alias = mediator.get_alias("AAPL", scope)
            self.assertEqual(mediator.restore_output(alias, scope), "AAPL")

        with self.assertRaises(ScopeNotFoundError):
            mediator.restore_output(alias, scope)

    def test_conflicting_catalog_aliases_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "multiple catalog entries"):
            FinScopeMediator(
                [
                    {"name": "Company A", "aliases": ["DUP"]},
                    {"name": "Company B", "aliases": ["DUP"]},
                ]
            )


if __name__ == "__main__":
    unittest.main()
