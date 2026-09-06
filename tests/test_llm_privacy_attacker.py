from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from benchmarks.llm_privacy_attacker import (
    AttackBatch,
    IdentityCandidate,
    IdentityTarget,
    LinkTarget,
    LlmPrivacyAttacker,
    average_precision,
    public_batch,
    stratified_bootstrap_interval,
    tpr_at_fpr,
    wilson_interval,
)


class _Completions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = next(self.responses)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


class _Client:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=_Completions(responses))


class LlmPrivacyAttackerTests(unittest.TestCase):
    def test_link_metrics_treat_tied_scores_as_one_threshold(self):
        labels = [True, True, False, False]
        scores = [0.5, 0.5, 0.5, 0.5]
        self.assertEqual(average_precision(labels, scores), 0.5)
        self.assertEqual(tpr_at_fpr(labels, scores), 0.0)
        self.assertEqual(stratified_bootstrap_interval(labels, scores, average_precision), [0.5, 0.5])
        interval = wilson_interval(5, 10)
        self.assertIsNotNone(interval)
        self.assertLess(interval[0], 0.5)
        self.assertGreater(interval[1], 0.5)

    def test_scores_validated_identity_and_link_predictions(self):
        identity = json.dumps(
            {
                "predictions": [
                    {"target_id": "t1", "ranking": ["C0001", "BAD"], "confidence": 0.9},
                    {"target_id": "t2", "ranking": ["C0002", "C0001"], "confidence": 0.8},
                ]
            }
        )
        links = json.dumps(
            {
                "predictions": [
                    {"pair_id": "p1", "same_probability": 0.9},
                    {"pair_id": "p2", "same_probability": 0.1},
                ]
            }
        )
        client = _Client([identity, links])
        attacker = LlmPrivacyAttacker(
            base_url="http://example.test/v1", model="test", client=client
        )
        batch = AttackBatch(
            benchmark="test",
            method="finscope",
            prior_level="K2",
            trace_length="5",
            candidates=[
                IdentityCandidate("A", {"kind": "a"}),
                IdentityCandidate("B", {"kind": "b"}),
            ],
            identity_targets=[
                IdentityTarget("t1", "A", {"visible": "a"}),
                IdentityTarget("t2", "B", {"visible": "b"}),
            ],
            link_targets=[
                LinkTarget("p1", True, {"h": "x"}, {"h": "x"}),
                LinkTarget("p2", False, {"h": "x"}, {"h": "y"}),
            ],
        )
        result = attacker.attack(batch)
        self.assertEqual(result["reid_at_1"], 1.0)
        self.assertEqual(result["reid_at_5"], 1.0)
        self.assertEqual(result["mrr"], 1.0)
        self.assertEqual(result["link_auc"], 1.0)
        self.assertEqual(result["link_auprc"], 1.0)
        self.assertEqual(result["identity_predictions"][0]["ranking"], ["A"])
        prompt = client.chat.completions.requests[0]["messages"][1]["content"]
        self.assertNotIn("truth_id", prompt)
        self.assertNotIn("same_entity", prompt)
        self.assertNotIn('"candidate_id"', prompt)
        self.assertIn('"option_id": "C0001"', prompt)

    def test_public_batch_removes_hidden_labels(self):
        batch = AttackBatch(
            "test",
            "method",
            "K1",
            "1",
            [IdentityCandidate("A", {})],
            [IdentityTarget("target", "A", {})],
            [LinkTarget("pair", True, {}, {})],
        )
        visible = public_batch(batch)
        encoded = json.dumps(visible)
        self.assertNotIn("truth_id", encoded)
        self.assertNotIn("same_entity", encoded)
        self.assertNotIn("candidate_id", encoded)


if __name__ == "__main__":
    unittest.main()
