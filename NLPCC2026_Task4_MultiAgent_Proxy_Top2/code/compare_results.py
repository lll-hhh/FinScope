#!/usr/bin/env python3
"""Build a compact comparison table from three NLPCC experiment summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONDITIONS = (
    ("plaintext_original", "plaintext_original"),
    ("global_direct_alias", "global_direct_alias"),
    ("scoped_finscope_alias", "scoped_finscope_alias"),
)


def _format(value: Any, key: str) -> str:
    if value is None:
        return "NA"
    if key in {
        "total_return",
        "max_drawdown_computed",
        "execution_success_rate",
        "external_identifier_exposure_rate",
    }:
        return f"{100 * float(value):.4f}%"
    if key in {"sharpe_ratio_computed", "mean_latency_s"}:
        return f"{float(value):.4f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for condition, folder in CONDITIONS:
        summary = json.loads((args.root / folder / "summary.json").read_text(encoding="utf-8"))
        summary["condition"] = condition
        rows.append(summary)

    comparison = {
        "experiment_id": "multiagent-proxy-top2-qwen3-8b-2025",
        "experiment_kind": "official starter multi-agent proxy integration study",
        "benchmark": "NLPCC2026 Shared Task 4",
        "track": "macro",
        "period": "2025-01-02 to 2025-12-31",
        "trading_days": 243,
        "top_rank": 2,
        "model": "Qwen/Qwen3-8B",
        "context_length": 32768,
        "conditions": rows,
    }
    args.output_json.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    columns = (
        ("Condition", "condition"),
        ("Days", "decision_days"),
        ("Trade days", "days_with_submitted_trades"),
        ("Return", "total_return"),
        ("Sharpe", "sharpe_ratio_computed"),
        ("MaxDD", "max_drawdown_computed"),
        ("Exec rate", "execution_success_rate"),
        ("Proxy errors", "error_count"),
        ("ETF exposure", "external_identifier_exposure_rate"),
        ("Aliases", "total_alias_occurrences"),
        ("Prompt tok", "total_prompt_tokens"),
        ("Completion tok", "total_completion_tokens"),
        ("Mean latency s", "mean_latency_s"),
    )
    lines = [
        "# NLPCC2026 Task 4 — Official-Starter Multi-Agent Proxy Study",
        "",
        "- Experiment ID: multiagent-proxy-top2-qwen3-8b-2025",
        "- Distinct from: benchmarks/run_nlpcc_real.py and its Qwen3.8-27B Top-20 report",
        "- Track: macro",
        "- Period: 2025-01-02 to 2025-12-31 (243 trading days)",
        "- News setting: top-rank=2 (research main experiment; not an official Top-20 leaderboard score)",
        "- Model: Qwen/Qwen3-8B, 32K context",
        "",
        "| " + " | ".join(title for title, _ in columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format(row.get(key), key) for _, key in columns) + " |")
    lines.extend(("", "## Integrity checks", ""))
    for row in rows:
        lines.append(
            "- {condition}: days={decision_days}, requests={request_count}, "
            "successful={successful_request_count}, errors={error_count}, attempted trades={trade_attempt_count}, "
            "executed={executed_trade_count}, rejected={rejected_trade_count}.".format(**row)
        )
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
