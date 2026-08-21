from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from finscope import (
    BenchmarkName,
    BenchmarkPrivacyAdapter,
    DisclosureLevel,
    EpisodeContext,
    LocalPrivacyAgent,
    ModelProfile,
    OpenAICompatibleChatModel,
    PrivacyRunConfig,
    enterprise_profile,
)


class _Message:
    content = "ok"


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


class _Completions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _Response()


class _Chat:
    def __init__(self) -> None:
        self.completions = _Completions()


class _Client:
    def __init__(self) -> None:
        self.chat = _Chat()


class ProviderAndBenchmarkTests(unittest.TestCase):
    def test_provider_passes_headers_without_exposing_secret_in_redacted_profile(self) -> None:
        profile = ModelProfile(
            "test", "model", "https://example.test/v1", "secret", {"X-Test": "token"}
        )
        client = _Client()
        model = OpenAICompatibleChatModel(profile, client=client)
        self.assertEqual(model("hello"), "ok")
        self.assertEqual(client.chat.completions.kwargs["extra_headers"], {"X-Test": "token"})
        self.assertNotIn("secret", repr(profile.redacted()))
        self.assertNotIn("token", repr(profile.redacted()))

    def test_enterprise_model_alias_is_explicit(self) -> None:
        with patch.dict(os.environ, {"EFUNDS_API_KEY": "x"}, clear=True):
            with self.assertRaises(ValueError):
                enterprise_profile("deepseek")

    def test_common_benchmark_adapter_runs_scope_lifecycle(self) -> None:
        agent = LocalPrivacyAgent([{"name": "贵州茅台", "sector_l1": "消费"}])
        adapter = BenchmarkPrivacyAdapter(
            agent,
            PrivacyRunConfig(disclosure_level=DisclosureLevel.P3),
        )
        context = EpisodeContext(
            BenchmarkName.NLPCC_2026_TASK4,
            "episode-1",
            "2026-08-21",
            "research-risk-trade",
        )
        adapter.open_episode(context)
        safe = adapter.sanitize_llm_input("分析贵州茅台", "episode-1")
        restored = adapter.restore_llm_output(safe, "episode-1")
        trace = adapter.close_episode("episode-1")
        self.assertNotIn("贵州茅台", safe)
        self.assertEqual(restored.value, "分析贵州茅台")
        self.assertEqual([item.channel for item in trace], ["llm_input", "llm_output"])


if __name__ == "__main__":
    unittest.main()
