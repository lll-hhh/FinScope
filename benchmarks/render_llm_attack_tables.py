"""Render paper-ready tables from the formal LLM privacy attack artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


METHOD_NAMES = {
    "fixed_alias": "Fixed Alias",
    "episode_alias": "Episode Alias",
    "finscope": "FinScope Adaptive",
}


def rows(path: Optional[Path]) -> List[Mapping[str, Any]]:
    if path is None or not path.is_file():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    values = value.get("rows", []) if isinstance(value, Mapping) else []
    return [item for item in values if isinstance(item, Mapping) and item.get("status") == "ok"]


def number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "--"
    return f"{float(value):.{digits}f}"


def estimate(value: Any, interval: Any) -> str:
    if value is None:
        return "--"
    point = float(value)
    if isinstance(interval, Sequence) and len(interval) == 2:
        return f"{point:.3f} [{float(interval[0]):.3f}, {float(interval[1]):.3f}]"
    return f"{point:.3f}"


def table(headers: Sequence[str], values: Iterable[Sequence[Any]]) -> List[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(item) for item in row) + " |" for row in values)
    return lines


def trace_rank(value: Any) -> int:
    if str(value) == "full":
        return 10**9
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**8


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stockbench", type=Path)
    parser.add_argument("--nlpcc", type=Path)
    parser.add_argument("--finvault", type=Path)
    parser.add_argument("--utility", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    attack_rows = rows(args.stockbench) + rows(args.nlpcc) + rows(args.finvault)
    full_rows = sorted(
        (row for row in attack_rows if str(row.get("trace_length")) == "full"),
        key=lambda row: (
            str(row.get("benchmark")),
            str(row.get("method")),
            str(row.get("prior_level")),
        ),
    )
    long_rows = sorted(
        (row for row in attack_rows if row.get("prior_level") == "K4"),
        key=lambda row: (
            str(row.get("benchmark")),
            str(row.get("method")),
            trace_rank(row.get("trace_length")),
        ),
    )

    lines = [
        "# Qwen3.5-4B Privacy-Attack Results",
        "",
        "The attacker is training-free and receives only the exact external-model view plus the public prior permitted by K1-K4. Canonical labels and the local restoration map are used only after inference for scoring.",
        "",
        "## Table A: Public-Prior Strength",
        "",
        "This table tests how much identity and cross-trajectory privacy remains when the attacker gains progressively stronger public information; each cell reports its actual target or pair count.",
        "",
    ]
    lines.extend(
        table(
            [
                "Benchmark",
                "Method",
                "Prior",
                "Identity n",
                "ReID@1 (95% CI) down",
                "ReID@5 down",
                "MRR down",
                "Link n",
                "Link AUC (95% CI) to .5",
                "Link AUPRC down",
                "TPR@1%FPR down",
            ],
            (
                (
                    row.get("benchmark"),
                    METHOD_NAMES.get(str(row.get("method")), row.get("method")),
                    row.get("prior_level"),
                    row.get("identity_targets"),
                    estimate(row.get("reid_at_1"), row.get("reid_at_1_ci95")),
                    number(row.get("reid_at_5")),
                    number(row.get("mrr")),
                    row.get("link_pairs"),
                    estimate(row.get("link_auc"), row.get("link_auc_ci95")),
                    number(row.get("link_auprc")),
                    number(row.get("link_tpr_at_1pct_fpr")),
                )
                for row in full_rows
            ),
        )
    )
    lines.extend(
        [
            "",
            "Metric note: ReID@1, ReID@5, MRR, ROC-AUC, average precision (AUPRC), and TPR@1%FPR are standard retrieval/verification metrics, not newly invented scores. The FinScope-specific part is the label-isolated construction of identity targets and balanced same/different-entity trajectory pairs from real external views. Wilson intervals are used for ReID; Link intervals use 1,000 stratified bootstrap resamples.",
            "",
            "## Table B: Privacy Risk versus Observed Trajectory Length",
            "",
            "This table fixes the strongest K4 prior and varies only how much history the attacker can observe, directly testing the long-horizon privacy claim.",
            "",
        ]
    )
    lines.extend(
        table(
            [
                "Benchmark",
                "Method",
                "Observed steps",
                "Identity n",
                "ReID@1 down",
                "Link n",
                "Link AUC to .5",
                "Link coverage",
            ],
            (
                (
                    row.get("benchmark"),
                    METHOD_NAMES.get(str(row.get("method")), row.get("method")),
                    row.get("trace_length"),
                    row.get("identity_targets"),
                    number(row.get("reid_at_1")),
                    row.get("link_pairs"),
                    number(row.get("link_auc")),
                    number(row.get("link_coverage")),
                )
                for row in long_rows
            ),
        )
    )
    lines.extend(
        [
            "",
            "Implementation note: StockBench steps are trading days, NLPCC steps are the official 2025 trading-day sequence, and FinVault steps are turns within one episode. FinVault is therefore a multi-turn generalization test, not evidence of cross-day behavior.",
            "",
            "## Table C: Development-Only Threshold Selection",
            "",
            "This table selects T only from StockBench development data: candidates that exceed the allowed native-utility loss are ineligible, and the remaining candidate with the lowest combined ReID/link risk is locked before testing.",
            "",
        ]
    )
    utility_rows: List[Mapping[str, Any]] = []
    if args.utility and args.utility.is_file():
        value = json.loads(args.utility.read_text(encoding="utf-8"))
        utility_rows = value.get("rows", []) if isinstance(value, Mapping) else []
    selected = None
    if args.calibration and args.calibration.is_file():
        value = json.loads(args.calibration.read_text(encoding="utf-8"))
        selected = float(value.get("threshold")) if value.get("threshold") is not None else None
    lines.extend(
        table(
            ["T", "Max utility loss down", "ReID@1 down", "Link AUC to .5", "Selected"],
            (
                (
                    number(row.get("threshold"), 2),
                    number(row.get("utility_loss")),
                    number(row.get("reid_at_1")),
                    number(row.get("link_auc")),
                    "yes" if selected is not None and float(row.get("threshold")) == selected else "",
                )
                for row in utility_rows
            ),
        )
    )
    lines.extend(
        [
            "",
            "Selection note: T is a policy threshold, not a privacy metric. The online system estimates attack risk from local cumulative exposure state, defers rotation while an old handle has unfinished dependencies, and rotates at the nearest safe checkpoint once estimated risk exceeds T.",
            "",
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.output}: {len(attack_rows)} attack rows")


if __name__ == "__main__":
    main()
