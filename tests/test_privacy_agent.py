from __future__ import annotations

import json
import re
import unittest

from finscope import (
    AmbiguousRestorationError,
    DisclosureLevel,
    EmpiricalDisclosurePolicy,
    JsonModelDisclosurePlanner,
    JsonModelRecoveryAuditor,
    LocalPrivacyAgent,
)


CATALOG = [
    {
        "canonical_id": "600519.SH",
        "name": "贵州茅台",
        "aliases": ["600519"],
        "asset_type": "股票",
        "market": "A股",
        "sector_l1": "消费",
        "sector_l2": "食品饮料",
        "sector_l3": "白酒",
        "size_bucket": "大盘",
    },
    {
        "canonical_id": "000858.SZ",
        "name": "五粮液",
        "aliases": ["000858"],
        "asset_type": "股票",
        "market": "A股",
        "sector_l1": "消费",
        "sector_l2": "食品饮料",
        "sector_l3": "白酒",
        "size_bucket": "大盘",
    },
]


class PrivacyAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = LocalPrivacyAgent(CATALOG)
        self.scope = self.agent.open_scope("task", "2026-08-21")

    def test_five_levels_reveal_progressively_coarser_master_data(self) -> None:
        outputs = {}
        for level in DisclosureLevel:
            outputs[level] = self.agent.sanitize(
                "分析贵州茅台", self.scope, disclosure_level=level
            )

        self.assertIn("大盘", outputs[DisclosureLevel.P1])
        self.assertIn("白酒", outputs[DisclosureLevel.P2])
        self.assertIn("消费", outputs[DisclosureLevel.P3])
        self.assertIn("A股", outputs[DisclosureLevel.P4])
        self.assertIn(">股票</fin-ref>", outputs[DisclosureLevel.P5])
        for output in outputs.values():
            self.assertNotIn("贵州茅台", output)
            self.assertNotIn("600519", output)

    def test_deterministic_description_cannot_equal_real_identifier(self) -> None:
        catalog = [
            {
                "canonical_id": "000941.SH",
                "name": "新能源指数",
                "asset_type": "指数",
                "sector_l1": "新能源",
            }
        ]
        agent = LocalPrivacyAgent(catalog)
        scope = agent.open_scope("descriptor-collision", "2026-08-21")
        safe = agent.sanitize("新能源指数", scope, disclosure_level="P3")
        self.assertNotIn(">新能源指数</fin-ref>", safe)
        self.assertIn(">新能源类指数</fin-ref>", safe)

    def test_same_semantics_keep_distinct_handles_and_restore_exactly(self) -> None:
        safe = self.agent.sanitize(
            ["贵州茅台", "五粮液"], self.scope, disclosure_level="P2"
        )
        aliases = [re.search(r"FS_ASSET_[A-Z2-9]{8}", item).group(0) for item in safe]
        self.assertNotEqual(aliases[0], aliases[1])
        self.assertIn("白酒股票", safe[0])
        self.assertIn("白酒股票", safe[1])

        restored = self.agent.restore_and_audit(safe, self.scope)
        self.assertEqual(restored.value, ["贵州茅台", "五粮液"])
        self.assertEqual(restored.status, "safe")

    def test_descriptor_without_handle_is_rejected_for_execution(self) -> None:
        self.agent.sanitize(["贵州茅台", "五粮液"], self.scope, disclosure_level="P2")
        with self.assertRaises(AmbiguousRestorationError):
            self.agent.restore_and_audit(
                {"asset": "白酒股票", "side": "buy", "quantity": 1},
                self.scope,
                execution=True,
            )

    def test_descriptor_in_reason_does_not_block_handle_bound_action(self) -> None:
        safe_asset = self.agent.sanitize(
            "贵州茅台", self.scope, disclosure_level="P2"
        )
        result = self.agent.validate_action(
            {
                "asset": safe_asset,
                "side": "buy",
                "quantity": 1,
                "reason": "白酒股票基本面稳健",
            },
            self.scope,
        )
        self.assertEqual(result.action["asset"], "贵州茅台")
        self.assertEqual(result.action["reason"], "白酒股票基本面稳健")

    def test_stale_handle_is_rejected(self) -> None:
        stale = '<fin-ref type="asset" id="FS_ASSET_ABCDEFGH">股票</fin-ref>'
        result = self.agent.restore_and_audit(stale, self.scope)
        self.assertEqual(result.status, "rejected")
        self.assertIn("unknown_handle", {issue.code for issue in result.issues})

    def test_action_round_trip_is_validated_locally(self) -> None:
        safe = self.agent.sanitize(
            {"asset": "贵州茅台", "side": "buy", "quantity": 2},
            self.scope,
            disclosure_level="P3",
        )
        validated = self.agent.validate_action(safe, self.scope)
        self.assertEqual(validated.action["asset"], "贵州茅台")
        self.assertEqual(validated.action["quantity"], 2)

    def test_scope_rotation_changes_handle(self) -> None:
        first = self.agent.sanitize("贵州茅台", self.scope)
        self.agent.close_scope(self.scope)
        new_scope = self.agent.open_scope("task", "2026-08-22")
        second = self.agent.sanitize("贵州茅台", new_scope)
        first_alias = re.search(r"FS_ASSET_[A-Z2-9]{8}", first).group(0)
        second_alias = re.search(r"FS_ASSET_[A-Z2-9]{8}", second).group(0)
        self.assertNotEqual(first_alias, second_alias)

    def test_model_planner_is_cached_and_hallucination_falls_back(self) -> None:
        calls = []

        def hallucinating_model(_prompt: str) -> str:
            calls.append(True)
            return json.dumps(
                {
                    "candidates": [
                        {
                            "level": "P%s" % index,
                            "descriptor": "贵州茅台龙头",
                            "used_attributes": [],
                        }
                        for index in range(1, 6)
                    ]
                },
                ensure_ascii=False,
            )

        planner = JsonModelDisclosurePlanner(hallucinating_model)
        agent = LocalPrivacyAgent(CATALOG, disclosure_planner=planner)
        scope = agent.open_scope("planner", "2026-08-21")
        first = agent.sanitize("贵州茅台", scope, disclosure_level="P2")
        second = agent.sanitize("贵州茅台", scope, disclosure_level="P2")
        self.assertEqual(len(calls), 1)
        self.assertIn("白酒股票", first)
        self.assertNotIn("龙头", first)
        self.assertEqual(first, second)

    def test_adaptive_mode_requires_calibration(self) -> None:
        with self.assertRaises(ValueError):
            self.agent.sanitize("贵州茅台", self.scope, adaptive=True)
        agent = LocalPrivacyAgent(
            CATALOG,
            adaptive_policy=EmpiricalDisclosurePolicy(
                {"research": "P2", "execution": "P5"},
                calibrated_on="pilot-v1",
            ),
        )
        scope = agent.open_scope("adaptive", "2026-08-21")
        self.assertIn("白酒股票", agent.sanitize("贵州茅台", scope, purpose="research", adaptive=True))
        self.assertIn(">股票</fin-ref>", agent.sanitize("贵州茅台", scope, purpose="execution", adaptive=True))

    def test_model_auditor_reports_but_cannot_change_mapping(self) -> None:
        auditor = JsonModelRecoveryAuditor(
            lambda _prompt: json.dumps(
                {
                    "issues": [
                        {
                            "code": "semantic_drift",
                            "severity": "warning",
                            "message": "reason changed",
                            "aliases": [],
                        }
                    ]
                }
            )
        )
        agent = LocalPrivacyAgent(CATALOG, recovery_auditor=auditor)
        scope = agent.open_scope("audit", "2026-08-21")
        safe = agent.sanitize("贵州茅台", scope)
        before = agent.mediator.get_local_mapping(scope)
        result = agent.restore_and_audit(safe, scope)
        after = agent.mediator.get_local_mapping(scope)
        self.assertEqual(result.status, "needs_retry")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
