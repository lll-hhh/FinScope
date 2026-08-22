from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from benchmarks.serve_privacy_proxy import (
    AliasMapper,
    IdentityCatalog,
    PrivacyController,
    ProxyConfig,
    stockbench_catalog,
)


def config(method: str, audit: Path) -> ProxyConfig:
    return ProxyConfig(
        benchmark="stockbench",
        method=method,
        upstream_url="http://127.0.0.1:1/v1",
        upstream_model="Qwen3.8-27B",
        audit_log=audit,
        disclosure_level="P3",
        seed="test-seed",
        timeout=1.0,
    )


class ExternalPrivacyProxyTests(unittest.TestCase):
    def test_episode_id_uses_latest_visible_stockbench_date(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = PrivacyController(
                config("vanilla", Path(directory) / "audit.jsonl"),
                stockbench_catalog(),
            )
            episode = controller.episode_id(
                {
                    "messages": [
                        {"role": "user", "content": "history 2025-03-01, today 2025-03-03"}
                    ]
                }
            )
            self.assertEqual(episode, "2025-03-03")

    def test_episode_alias_rotates_and_restores(self):
        catalog = IdentityCatalog(stockbench_catalog())
        first = AliasMapper(catalog, "EA", b"secret", "2025-03-03")
        repeated = AliasMapper(catalog, "EA", b"secret", "2025-03-03")
        second = AliasMapper(catalog, "EA", b"secret", "2025-03-04")
        raw = {"symbol": "AAPL", "text": "Apple and Microsoft"}
        protected = first.sanitize(raw)
        self.assertEqual(protected, repeated.sanitize(raw))
        self.assertNotEqual(protected, second.sanitize(raw))
        self.assertEqual(
            first.restore(protected),
            {"symbol": "AAPL", "text": "AAPL and MSFT"},
        )

    def test_deletion_removes_catalog_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = PrivacyController(
                config("deletion", Path(directory) / "audit.jsonl"),
                stockbench_catalog(),
            )
            outbound, _ = controller.transform(
                {
                    "model": "model",
                    "messages": [{"role": "user", "content": "Compare AAPL and Microsoft"}],
                },
                "2025-03-03",
            )
            text = outbound["messages"][0]["content"]
            self.assertNotIn("AAPL", text)
            self.assertNotIn("Microsoft", text)
            self.assertIn("REDACTED", text)

    def test_finscope_response_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = PrivacyController(
                config("finscope", Path(directory) / "audit.jsonl"),
                stockbench_catalog(),
            )
            outbound, state = controller.transform(
                {
                    "model": "model",
                    "messages": [{"role": "user", "content": "Choose AAPL"}],
                },
                "2025-03-03",
            )
            protected = outbound["messages"][0]["content"]
            self.assertIn("<fin-ref", protected)
            response = {
                "choices": [{"message": {"role": "assistant", "content": protected}}],
                "usage": {},
            }
            restored, status, exact, issues = controller.restore(response, state)
            self.assertEqual(status, "safe")
            self.assertTrue(exact)
            self.assertEqual(issues, [])
            self.assertIn("AAPL", restored["choices"][0]["message"]["content"])

    def test_proxy_metadata_is_not_forwarded_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = PrivacyController(
                config("vanilla", Path(directory) / "audit.jsonl"),
                stockbench_catalog(),
            )
            outbound, _ = controller.transform(
                {
                    "model": "proxy-model",
                    "messages": [{"role": "user", "content": "Choose AAPL"}],
                    "finscope_episode": "2025-03-03",
                    "finscope_role": "decision_agent",
                },
                "2025-03-03",
            )
            self.assertNotIn("finscope_episode", outbound)
            self.assertNotIn("finscope_role", outbound)


if __name__ == "__main__":
    unittest.main()
