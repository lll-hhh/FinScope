from __future__ import annotations

import json
import re
import unittest

from finscope import (
    FinScopeMediator,
    JsonModelEntityRecognizer,
    PrivacyLevel,
    ResidualScanPolicy,
)


class FinScopeRecognizerTests(unittest.TestCase):
    def test_residual_scan_gate_cools_down_and_periodically_probes(self) -> None:
        calls = []

        def fake_model(_prompt: str) -> str:
            calls.append(True)
            return json.dumps({"entities": []})

        mediator = FinScopeMediator(
            entity_recognizer=JsonModelEntityRecognizer(fake_model),
            residual_scan_policy=ResidualScanPolicy(
                warmup_scans=1,
                no_new_threshold=1,
                probe_interval=2,
            ),
        )
        scope = mediator.open_scope("scan-gate-task", "2026-08-15")

        mediator.sanitize_prompt("稳定的研究模板", scope)
        mediator.sanitize_prompt("稳定的研究模板", scope)
        mediator.sanitize_prompt("稳定的研究模板", scope)
        mediator.sanitize_prompt("稳定的研究模板", scope)

        self.assertEqual(len(calls), 2)
        metrics = mediator.get_metrics(scope)
        self.assertGreaterEqual(metrics["recognizer_skips"], 2)
        self.assertEqual(metrics["recognizer_probes"], 1)

    def test_scan_gate_wakes_on_risk_signal_and_force_flag(self) -> None:
        calls = []

        def fake_model(_prompt: str) -> str:
            calls.append(True)
            return json.dumps({"entities": []})

        mediator = FinScopeMediator(
            entity_recognizer=JsonModelEntityRecognizer(fake_model),
            residual_scan_policy=ResidualScanPolicy(
                warmup_scans=1,
                no_new_threshold=1,
                probe_interval=20,
            ),
        )
        scope = mediator.open_scope("scan-wake-task", "2026-08-15")

        mediator.sanitize_prompt("稳定模板", scope)
        mediator.sanitize_prompt("稳定模板", scope)
        mediator.sanitize_prompt("新代码 XYZ", scope)
        mediator.sanitize_prompt("仍然稳定", scope, force_model_scan=True)

        self.assertEqual(len(calls), 3)
    def test_known_list_is_replaced_before_residual_model_call_and_coreference_reuses_it(self) -> None:
        observed = {}

        def fake_model(prompt: str) -> str:
            text = prompt.split("INPUT:\n", 1)[1].split("\n\nJSON:", 1)[0]
            observed["input"] = text
            alias = re.search(r"FS_ASSET_[A-Z2-9]{8}", text).group(0)
            return json.dumps(
                {
                    "entities": [
                        {
                            "text": "该股",
                            "type": "reference",
                            "refers_to": alias,
                            "risk": 2,
                        },
                        {
                            "text": "增持",
                            "type": "action",
                            "canonical": "buy",
                            "risk": 4,
                        },
                    ]
                },
                ensure_ascii=False,
            )

        mediator = FinScopeMediator(
            [{"name": "Apple Inc.", "aliases": ["AAPL"]}],
            entity_recognizer=JsonModelEntityRecognizer(fake_model),
        )
        scope = mediator.open_scope("residual-task", "2026-08-15")

        sanitized = mediator.sanitize_prompt("AAPL：该股建议增持", scope)

        self.assertNotIn("AAPL", observed["input"])
        self.assertIn("FS_ASSET_", observed["input"])
        self.assertGreaterEqual(sanitized.count("FS_ASSET_"), 2)
        self.assertNotIn("FS_REF_", sanitized)
        self.assertIn("FS_ACTION_", sanitized)
        self.assertEqual(
            mediator.restore_output(sanitized, scope),
            "Apple Inc.：Apple Inc.建议增持",
        )
        asset_alias = re.search(r"FS_ASSET_[A-Z2-9]{8}", sanitized).group(0)
        action_alias = re.search(r"FS_ACTION_[A-Z2-9]{8}", sanitized).group(0)
        validated = mediator.validate_action(
            {"asset": asset_alias, "side": action_alias, "quantity": 1},
            scope,
        )
        self.assertEqual(validated.action["side"], "buy")

    def test_homonymous_surface_forms_use_span_specific_aliases(self) -> None:
        def fake_model(_prompt: str) -> str:
            return json.dumps(
                {
                    "entities": [
                        {"text": "ABC", "type": "asset", "occurrence": 1},
                        {"text": "ABC", "type": "institution", "occurrence": 2},
                    ]
                }
            )

        mediator = FinScopeMediator(entity_recognizer=JsonModelEntityRecognizer(fake_model))
        scope = mediator.open_scope("homonym-task", "2026-08-15")

        sanitized = mediator.sanitize_prompt("ABC 发布公告，ABC 资产上涨", scope)

        self.assertIn("FS_ASSET_", sanitized)
        self.assertIn("FS_ORG_", sanitized)
        types = {record["type"] for record in mediator.get_mapping_records(scope)}
        self.assertIn("asset", types)
        self.assertIn("institution", types)

    def test_adaptive_policy_escalates_on_execution_state(self) -> None:
        mediator = FinScopeMediator(
            [{"name": "Apple Inc.", "aliases": ["AAPL"]}],
        )
        scope = mediator.open_scope(
            "adaptive-task",
            "2026-08-15",
            privacy_level=PrivacyLevel.LOW,
        )

        sanitized = mediator.sanitize_tool_result(
            {"orders": [{"symbol": "AAPL", "quantity": 10}]},
            scope,
        )

        self.assertIn("FS_ASSET_", repr(sanitized))
        status = mediator.get_privacy_status(scope)
        self.assertEqual(status["effective_level"], "critical")
        self.assertIn("execution-state", status["reasons"])

    def test_privacy_level_controls_action_masking_and_only_escalates(self) -> None:
        recognizer = JsonModelEntityRecognizer(
            lambda _prompt: json.dumps(
                {
                    "entities": [
                        {
                            "text": "增持",
                            "type": "action",
                            "canonical": "buy",
                            "risk": 2,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        mediator = FinScopeMediator(entity_recognizer=recognizer)
        scope = mediator.open_scope(
            "level-task",
            "2026-08-15",
            privacy_level=PrivacyLevel.LOW,
        )

        low = mediator.sanitize_prompt("建议增持", scope)
        high = mediator.sanitize_prompt(
            "建议增持",
            scope,
            privacy_level=PrivacyLevel.HIGH,
        )

        self.assertEqual(low, "建议增持")
        self.assertIn("FS_ACTION_", high)
        self.assertEqual(mediator.get_privacy_status(scope)["effective_level"], "high")

    def test_alias_restore_and_action_validation_handle_wrappers(self) -> None:
        mediator = FinScopeMediator(
            [{"name": "Apple Inc.", "aliases": ["AAPL"]}],
        )
        scope = mediator.open_scope("wrapper-task", "2026-08-15")
        alias = mediator.get_alias("AAPL", scope)

        restored = mediator.restore_output(f"`{alias}`'s trend", scope)
        result = mediator.validate_action(
            {"asset": f"{alias}'s", "side": "buy", "quantity": 1},
            scope,
        )

        self.assertEqual(restored, "`Apple Inc.`'s trend")
        self.assertEqual(result.action["asset"], "Apple Inc.")

    def test_conversation_rotation_prevents_long_term_alias_linkage(self) -> None:
        mediator = FinScopeMediator(["Apple Inc."])
        first = mediator.open_scope(
            "same-task", "2026-08-15", conversation_id="conversation-a"
        )
        second = mediator.open_scope(
            "same-task", "2026-08-15", conversation_id="conversation-b"
        )

        self.assertNotEqual(
            mediator.get_alias("Apple Inc.", first),
            mediator.get_alias("Apple Inc.", second),
        )

    def test_local_model_automatically_maps_all_supported_entity_types(self) -> None:
        raw = "华夏基金的稳健一号组合使用红利策略，账户ACC-42持有贵州茅台。"
        detected = (
            ("华夏基金", "institution"),
            ("稳健一号", "portfolio"),
            ("红利策略", "strategy"),
            ("ACC-42", "account"),
            ("贵州茅台", "asset"),
        )

        def fake_model(_prompt: str) -> str:
            return json.dumps(
                {
                    "entities": [
                        {"text": text, "type": entity_type, "canonical": None}
                        for text, entity_type in detected
                    ]
                },
                ensure_ascii=False,
            )

        mediator = FinScopeMediator(
            entity_recognizer=JsonModelEntityRecognizer(fake_model)
        )
        scope = mediator.open_scope("multi-entity-task", "2026-08-15")

        sanitized = mediator.sanitize_prompt(raw, scope)

        for prefix in (
            "FS_ORG_",
            "FS_PORTFOLIO_",
            "FS_STRATEGY_",
            "FS_ACCOUNT_",
            "FS_ASSET_",
        ):
            self.assertIn(prefix, sanitized)
        self.assertEqual(mediator.restore_output(sanitized, scope), raw)
        self.assertEqual(mediator.get_metrics(scope)["entities_registered"], 5)

    def test_local_model_spans_create_one_mapping_for_name_and_ticker(self) -> None:
        def fake_model(prompt: str) -> str:
            text = prompt.split("INPUT:\n", 1)[1].split("\n\nJSON:", 1)[0]
            entities = []
            for token in ("AAPL", "Apple Inc."):
                start = text.find(token)
                if start >= 0:
                    entities.append(
                        {
                            "start": start,
                            "end": start + len(token),
                            "type": "asset",
                            "canonical": "Apple Inc.",
                        }
                    )
            return json.dumps({"entities": entities})

        recognizer = JsonModelEntityRecognizer(fake_model)
        mediator = FinScopeMediator(entity_recognizer=recognizer)
        scope = mediator.open_scope("model-task", "2026-08-15")

        sanitized = mediator.sanitize_prompt("研究 AAPL 和 Apple Inc.", scope)
        alias = mediator.get_alias("Apple Inc.", scope)

        self.assertEqual(sanitized, "研究 %s 和 %s" % (alias, alias))
        self.assertEqual(mediator.restore_output(sanitized, scope), "研究 Apple Inc. 和 Apple Inc.")
        self.assertGreaterEqual(mediator.get_metrics(scope)["recognizer_calls"], 1)

    def test_malformed_model_output_falls_back_to_catalog(self) -> None:
        recognizer = JsonModelEntityRecognizer(
            lambda _prompt: "not-json",
            fallback=None,
        )
        mediator = FinScopeMediator(
            [{"name": "Apple Inc.", "aliases": ["AAPL"]}],
            entity_recognizer=recognizer,
        )
        scope = mediator.open_scope("fallback-task", "2026-08-15")

        anonymized = mediator.sanitize_prompt("分析 AAPL", scope)
        self.assertNotIn("AAPL", anonymized)
        self.assertIn("FS_ASSET_", anonymized)

    def test_security_master_overrides_a_model_type_error(self) -> None:
        recognizer = JsonModelEntityRecognizer(
            lambda _prompt: json.dumps(
                {
                    "entities": [
                        {
                            "text": "贵州茅台",
                            "type": "institution",
                            "canonical": None,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        mediator = FinScopeMediator(
            [{"name": "贵州茅台", "aliases": ["600519"]}],
            entity_recognizer=recognizer,
        )
        scope = mediator.open_scope("type-check-task", "2026-08-15")

        anonymized = mediator.sanitize_prompt("分析贵州茅台", scope)

        self.assertIn("FS_ASSET_", anonymized)
        self.assertNotIn("FS_ORG_", anonymized)
        self.assertEqual(len(mediator.get_local_mapping(scope)), 1)

    def test_bad_model_span_cannot_replace_surrounding_prose(self) -> None:
        def bad_model(_prompt: str) -> str:
            return json.dumps(
                {
                    "entities": [
                        {
                            "start": 0,
                            "end": 4,
                            "type": "asset",
                            "canonical": "AAPL",
                        }
                    ]
                }
            )

        mediator = FinScopeMediator(
            [{"name": "Apple Inc.", "aliases": ["AAPL"]}],
            entity_recognizer=JsonModelEntityRecognizer(bad_model),
        )
        scope = mediator.open_scope("bad-span-task", "2026-08-15")
        anonymized = mediator.sanitize_prompt("请分析 AAPL", scope)

        self.assertTrue(anonymized.startswith("请分析 "))
        self.assertNotIn("AAPL", anonymized)
        self.assertEqual(len(mediator.get_local_mapping(scope)), 1)


if __name__ == "__main__":
    unittest.main()
