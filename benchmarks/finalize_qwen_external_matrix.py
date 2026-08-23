"""Fill Qwen StockBench/FinVault rows after a complete external matrix run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Dict, Mapping


METHOD_LABELS = {
    "vanilla": "Vanilla",
    "deletion": "Deletion",
    "llm_rewrite": "LLM Rewrite",
    "global_alias": "Global Alias",
    "episode_alias": "Episode Alias",
    "finscope": "FinScope P3",
}


def percent(value: Any) -> str:
    return f"{100 * float(value):.2f}%"


def number(value: Any) -> str:
    return f"{float(value):.3f}"


def optional_percent(value: Any, *, missing: str = "TBD") -> str:
    return missing if value is None else percent(value)


def row_text(row: Mapping[str, Any]) -> str:
    benchmark = str(row["benchmark"])
    method = str(row["method"])
    native = row["native"]
    privacy = row["privacy"]
    audit = row["audit"]
    if benchmark == "stockbench":
        native_cells = [
            percent(native["total_return"]),
            number(native["sortino_annual"]),
            percent(native["max_drawdown"]),
            number(native["sharpe"]),
        ]
    elif benchmark == "finvault":
        native_cells = [
            percent(native["benign_success"]),
            percent(native["attack_success"]),
            percent(native["violation_free"]),
            percent(native["over_refusal"]),
        ]
    else:
        raise ValueError(f"unsupported benchmark: {benchmark}")
    decision = row.get("decision_preservation")
    decision_rate = (
        None if not isinstance(decision, Mapping) else decision.get("rate")
    )
    continuity = row.get("reference_continuity")
    continuity_rate = (
        None if not isinstance(continuity, Mapping) else continuity.get("episode_rate")
    )
    if method == "vanilla":
        decision_cell = "ref."
    else:
        decision_cell = optional_percent(decision_rate)
    continuity_cell = (
        "--"
        if method in {"vanilla", "deletion", "llm_rewrite"} and continuity_rate is None
        else optional_percent(continuity_rate, missing="N/A")
    )
    exact_action = audit.get("exact_action_restore_rate")
    exact_action_cell = (
        "--" if method in {"vanilla", "deletion", "llm_rewrite"} and exact_action is None
        else optional_percent(exact_action)
    )
    delta = row.get("token_delta_vs_vanilla")
    token_delta = "ref." if method == "vanilla" else f"{100 * float(delta):+.1f}%"
    cells = [
        benchmark.replace("stockbench", "StockBench").replace("finvault", "FinVault"),
        "Qwen3.8-27B",
        METHOD_LABELS[method],
        *native_cells,
        decision_cell,
        continuity_cell,
        exact_action_cell,
        percent(privacy["reid_at_1"]),
        number(privacy["link_auc"]),
        token_delta,
        f"{float(audit['e2e_p95_ms']) / 1000:.3f} s",
    ]
    return "| " + " | ".join(cells) + " |"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--document", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    rows = summary.get("rows", [])
    external = {
        (row["benchmark"], row["method"]): row
        for row in rows
        if row.get("benchmark") in {"stockbench", "finvault"}
    }
    expected = {(benchmark, method) for benchmark in ("stockbench", "finvault") for method in METHOD_LABELS}
    if set(external) != expected:
        raise SystemExit(f"expected 12 external rows, found {len(external)}")
    incomplete = [key for key, row in external.items() if not row.get("complete")]
    if incomplete:
        raise SystemExit(f"refusing to finalize incomplete rows: {incomplete}")

    text = args.document.read_text(encoding="utf-8")
    for key, row in external.items():
        benchmark, method = key
        prefix = (
            rf"^\| {'StockBench' if benchmark == 'stockbench' else 'FinVault'} "
            rf"\| Qwen3\.8-27B \| {re.escape(METHOD_LABELS[method])} \|.*$"
        )
        text, count = re.subn(prefix, row_text(row), text, count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"could not replace document row: {key}")
    args.document.write_text(text, encoding="utf-8")
    print(f"updated 12 Qwen rows in {args.document}")


if __name__ == "__main__":
    main()
