import unittest

from finscope import (
    AdaptiveReplacementController,
    AdaptiveRuntime,
    AttackObservation,
    DevPolicyResult,
    DisclosureLevel,
    ExposureState,
    ReplacementDecision,
    RiskEstimator,
    TaskDependencyState,
    calibrate_threshold,
)


class AdaptiveControllerTests(unittest.TestCase):
    def estimator(self):
        rows = []
        for count in (1, 10, 50, 100):
            state = ExposureState(
                alias_occurrences=count,
                age_days=count,
                visible_roles={"research", "risk"},
                market_events=count,
                trade_events=count // 2,
                distinct_assets={"A"} if count < 50 else {"A", "B", "C"},
                high_risk_events=count // 20,
            )
            rows.append(AttackObservation(state.features(), count / 100.0, 0.5 + count / 200.0))
        return RiskEstimator().fit(rows)

    def test_threshold_is_calibrated_under_utility_constraint(self):
        threshold = calibrate_threshold(
            [
                DevPolicyResult(0.2, 0.08, 0.6, 0.7),
                DevPolicyResult(0.5, 0.03, 0.3, 0.56),
            ],
            max_utility_loss=0.05,
        )
        self.assertEqual(threshold, 0.5)

    def test_dependency_defers_rotation_until_checkpoint(self):
        controller = AdaptiveReplacementController(self.estimator(), threshold=0.2)
        controller.bind_scope("scope-old")
        decision = controller.observe_call(
            alias_occurrences=50,
            elapsed_days=20,
            visible_roles=("research", "risk"),
            field_risk=3,
            dependencies=TaskDependencyState(pending_action=True),
        )
        self.assertEqual(decision.decision, ReplacementDecision.REPLACE_AT_CHECKPOINT)
        self.assertGreaterEqual(decision.level, DisclosureLevel.P3)
        checkpoint = controller.observe_call(
            dependencies=TaskDependencyState(pending_action=True),
            safe_checkpoint=True,
        )
        self.assertEqual(checkpoint.decision, ReplacementDecision.REPLACE_NOW)

    def test_rotation_resets_exposure_without_exporting_aliases(self):
        controller = AdaptiveReplacementController(self.estimator(), threshold=0.2)
        controller.bind_scope("scope-old")
        controller.observe_call(alias_occurrences=50, elapsed_days=10)
        reset = controller.reset_session("scope-new", {"research_summary": "sector allocation"})
        self.assertEqual(reset.old_scope_id, "scope-old")
        self.assertEqual(reset.new_scope_id, "scope-new")
        self.assertEqual(controller.exposure.alias_occurrences, 0)
        self.assertEqual(controller.rotation_count, 1)
        with self.assertRaises(ValueError):
            controller.reset_session("scope-next", {"summary": "FS_ASSET_ABCDEF12"})

    def test_runtime_rotates_scope_before_new_session(self):
        from finscope import LocalPrivacyAgent

        agent = LocalPrivacyAgent(
            [
                {
                    "canonical_id": "AAPL",
                    "name": "Apple",
                    "asset_type": "stock",
                    "market": "US",
                    "sector_l1": "Technology",
                    "sector_l2": "Software",
                    "sector_l3": "Consumer technology",
                    "size_bucket": "large",
                }
            ]
        )
        controller = AdaptiveReplacementController(self.estimator(), threshold=0.1)
        runtime = AdaptiveRuntime(agent, controller)
        scope = agent.open_scope("task", "2026-09-05")
        protected, level = runtime.prepare({"asset": "AAPL"}, scope)
        self.assertNotEqual(protected, {"asset": "AAPL"})
        self.assertIsInstance(level, DisclosureLevel)
        new_scope, reset = runtime.rotate_at_checkpoint(scope, {"summary": "keep technology exposure"})
        self.assertNotEqual(new_scope.id, scope.id)
        self.assertEqual(reset.old_scope_id, scope.id)


if __name__ == "__main__":
    unittest.main()
