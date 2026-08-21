"""Merge method-sharded NLPCC runs after parallel GPU execution."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Dict, List, Mapping, Sequence

from benchmarks.run_nlpcc_real import FUND_POOL, METHODS, percentile, render_markdown


COMPATIBILITY_FIELDS = (
    "benchmark",
    "prompt_version",
    "model",
    "model_revision",
    "finscope_commit",
    "finscope_disclosure_level",
    "start_date",
    "end_date",
    "trading_days",
    "fund_pool",
    "news_sources",
    "official_rank_threshold",
    "merged_news_cap",
    "price_lookback_days",
    "commission_rate",
    "initial_capital",
    "temperature",
    "do_sample",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _max_drawdown_duration(values: Sequence[float]) -> int:
    peak = float("-inf")
    duration = 0
    longest = 0
    for value in values:
        if value >= peak:
            peak = value
            duration = 0
        else:
            duration += 1
            longest = max(longest, duration)
    return longest


def compute_expanded_metrics(
    records: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[float]],
    summaries: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Derive detailed finance, continuity, privacy, and cost metrics."""

    vanilla_rows = {
        row["date"]: row for row in records if row["method"] == "vanilla"
    }
    expanded: Dict[str, Any] = {}
    for method in METHODS:
        rows = [row for row in records if row["method"] == method]
        values = list(histories[method])
        daily_returns = [
            values[index] / values[index - 1] - 1
            for index in range(1, len(values))
        ]
        negative_returns = [value for value in daily_returns if value < 0]
        positive_returns = [value for value in daily_returns if value > 0]
        fifth_percentile = percentile(daily_returns, 0.05)
        tail_returns = [value for value in daily_returns if value <= fifth_percentile]
        periods = len(daily_returns)
        annualized_return = (
            (values[-1] / values[0]) ** (252 / periods) - 1
            if periods and values[0] > 0
            else 0.0
        )
        annualized_volatility = (
            statistics.stdev(daily_returns) * math.sqrt(252)
            if len(daily_returns) > 1
            else 0.0
        )
        summary = summaries[method]
        max_drawdown = float(summary["max_drawdown"])

        common_valid = []
        asset_matches = []
        action_matches = []
        for row in rows:
            vanilla = vanilla_rows[row["date"]]
            both_valid = bool(row["valid"] and vanilla["valid"])
            common_valid.append(both_valid)
            current_action = row.get("restored_action") or {}
            vanilla_action = vanilla.get("restored_action") or {}
            if both_valid:
                asset_matches.append(
                    current_action.get("asset") == vanilla_action.get("asset")
                )
                action_matches.append(
                    current_action.get("action") == vanilla_action.get("action")
                )

        parsed_count = sum(bool(row["parsed"]) for row in rows)
        valid_count = sum(bool(row["valid"]) for row in rows)
        executed_count = sum(bool(row["executed"]) for row in rows)
        rejection_counts = Counter(
            str(row["rejection_reason"])
            for row in rows
            if not row["executed"] and row.get("rejection_reason")
        )
        valid_actions = [
            str((row.get("restored_action") or {}).get("action", "unknown"))
            for row in rows
            if row["valid"]
        ]
        action_counts = Counter(valid_actions)
        executed_trade_count = sum(
            bool(row["executed"])
            and (row.get("restored_action") or {}).get("action") in {"buy", "sell"}
            for row in rows
        )

        preprocess = [float(row["preprocess_ms"]) for row in rows]
        postprocess = [float(row["postprocess_ms"]) for row in rows]
        local = [before + after for before, after in zip(preprocess, postprocess)]
        model = [float(row["model_latency_ms"]) for row in rows]
        e2e = [local_ms + model_ms for local_ms, model_ms in zip(local, model)]
        input_tokens = [int(row["input_tokens"]) for row in rows]
        output_tokens = [int(row["output_tokens"]) for row in rows]
        total_output_tokens = sum(output_tokens)
        total_model_seconds = sum(model) / 1000

        expanded[method] = {
            "finance": {
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_volatility,
                "calmar_ratio": annualized_return / max_drawdown if max_drawdown else 0.0,
                "average_daily_return": _mean(daily_returns),
                "positive_day_rate": len(positive_returns) / periods if periods else 0.0,
                "negative_day_rate": len(negative_returns) / periods if periods else 0.0,
                "best_daily_return": max(daily_returns, default=0.0),
                "worst_daily_return": min(daily_returns, default=0.0),
                "historical_var_95": max(0.0, -fifth_percentile),
                "historical_cvar_95": max(0.0, -_mean(tail_returns)),
                "max_drawdown_duration_days": _max_drawdown_duration(values),
                "executed_trade_count": executed_trade_count,
                "final_cash": float(rows[-1]["cash"]) if rows else 0.0,
            },
            "continuity": {
                "parsed_count": parsed_count,
                "parse_success_rate": parsed_count / len(rows) if rows else 0.0,
                "valid_count": valid_count,
                "valid_given_parsed_rate": valid_count / parsed_count if parsed_count else 0.0,
                "executed_count": executed_count,
                "execution_given_valid_rate": executed_count / valid_count if valid_count else 0.0,
                "workflow_interruption_rate": 1 - executed_count / len(rows) if rows else 0.0,
                "common_valid_days": sum(common_valid),
                "asset_agreement_given_common_valid": _mean(asset_matches),
                "action_agreement_given_common_valid": _mean(action_matches),
                "action_counts": dict(sorted(action_counts.items())),
                "rejection_counts": dict(sorted(rejection_counts.items())),
                "malformed_output_count": rejection_counts.get(
                    "model output is not parseable JSON", 0
                ),
                "restoration_audit_rejection_count": sum(
                    count
                    for reason, count in rejection_counts.items()
                    if reason.startswith("restoration audit failed:")
                ),
                "execution_rejection_count": sum(
                    count
                    for reason, count in rejection_counts.items()
                    if reason in {
                        "cannot sell an empty holding",
                        "buy amount exceeds current cash",
                    }
                ),
            },
            "privacy": {
                "direct_identifier_leak_count": sum(
                    bool(row["direct_identifier_leak"]) for row in rows
                ),
                "direct_identifier_leak_rate": summary[
                    "direct_identifier_leak_rate"
                ],
                "cross_day_unique_link_rate": summary[
                    "cross_day_unique_link_rate"
                ],
            },
            "cost": {
                "total_input_tokens": sum(input_tokens),
                "total_output_tokens": total_output_tokens,
                "average_input_tokens": _mean(input_tokens),
                "p95_input_tokens": percentile(input_tokens, 0.95),
                "average_output_tokens": _mean(output_tokens),
                "p95_output_tokens": percentile(output_tokens, 0.95),
                "average_model_latency_ms": _mean(model),
                "p95_model_latency_ms": percentile(model, 0.95),
                "average_preprocess_ms": _mean(preprocess),
                "p95_preprocess_ms": percentile(preprocess, 0.95),
                "average_postprocess_ms": _mean(postprocess),
                "p95_postprocess_ms": percentile(postprocess, 0.95),
                "average_local_overhead_ms": _mean(local),
                "p95_local_overhead_ms": percentile(local, 0.95),
                "average_e2e_latency_ms": _mean(e2e),
                "p50_e2e_latency_ms": percentile(e2e, 0.50),
                "p95_e2e_latency_ms": percentile(e2e, 0.95),
                "total_model_time_hours": total_model_seconds / 3600,
                "aggregate_output_tokens_per_second": (
                    total_output_tokens / total_model_seconds
                    if total_model_seconds > 0
                    else 0.0
                ),
            },
        }

    vanilla_input = expanded["vanilla"]["cost"]["average_input_tokens"]
    for method in METHODS:
        average_input = expanded[method]["cost"]["average_input_tokens"]
        expanded[method]["cost"]["input_token_overhead_vs_vanilla"] = (
            average_input / vanilla_input - 1 if vanilla_input else 0.0
        )
    return {
        "by_method": expanded,
        "not_measured": [
            "Asset-ReID@1/@5",
            "Pool-Recovery F1",
            "Holding-Inference F1",
            "Weight-Inference MAE from an attacker",
            "Cross-Day-Link AUC from an attacker",
            "Action/Intent Inference",
            "Unsafe Repair Rate",
            "monetary API cost, GPU energy, and peak GPU memory",
        ],
    }


def merge_results(documents: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not documents:
        raise ValueError("at least one input result is required")
    reference = documents[0]["metadata"]
    for document in documents[1:]:
        metadata = document["metadata"]
        mismatches = [
            field
            for field in COMPATIBILITY_FIELDS
            if metadata.get(field) != reference.get(field)
        ]
        if mismatches:
            raise ValueError("incompatible result metadata: %s" % ", ".join(mismatches))

    table_by_method: Dict[str, Dict[str, Any]] = {}
    records: List[Dict[str, Any]] = []
    histories: Dict[str, List[float]] = {}
    source_files: List[str] = []
    for document in documents:
        for row in document["main_table"]:
            method = row["method"]
            if method in table_by_method:
                raise ValueError("duplicate method %r" % method)
            table_by_method[method] = dict(row)
        records.extend(dict(row) for row in document["daily_records"])
        for method, values in document["portfolio_value_history"].items():
            if method in histories:
                raise ValueError("duplicate portfolio history %r" % method)
            histories[method] = list(values)
        source_files.extend(document["metadata"].get("source_result_files", ()))

    missing = set(METHODS) - set(table_by_method)
    if missing:
        raise ValueError("missing methods: %s" % sorted(missing))
    vanilla_by_date = {
        row["date"]: row for row in records if row["method"] == "vanilla"
    }
    for method, summary in table_by_method.items():
        rows = [row for row in records if row["method"] == method]
        matches = []
        weight_errors = []
        for row in rows:
            vanilla = vanilla_by_date.get(row["date"])
            if vanilla is None:
                raise ValueError("missing Vanilla record for %s" % row["date"])
            current_action = row.get("restored_action") or {}
            vanilla_action = vanilla.get("restored_action") or {}
            matches.append(
                row["valid"]
                and vanilla["valid"]
                and current_action.get("asset") == vanilla_action.get("asset")
                and current_action.get("action") == vanilla_action.get("action")
            )
            weight_errors.extend(
                abs(
                    row["portfolio_weights"].get(asset, 0.0)
                    - vanilla["portfolio_weights"].get(asset, 0.0)
                )
                for asset in FUND_POOL
            )
        summary["decision_agreement_with_vanilla"] = (
            sum(matches) / len(matches) if matches else 0.0
        )
        summary["portfolio_weight_mae_vs_vanilla"] = (
            statistics.mean(weight_errors) if weight_errors else 0.0
        )

    method_order = {method: index for index, method in enumerate(METHODS)}
    records.sort(key=lambda row: (row["date"], method_order[row["method"]]))
    metadata = dict(reference)
    metadata.update(
        {
            "methods": list(METHODS),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "execution_mode": "method-sharded across GPUs 4, 5, and 6",
            "source_result_files": source_files,
        }
    )
    result = {
        "metadata": metadata,
        "main_table": [table_by_method[method] for method in METHODS],
        "daily_records": records,
        "portfolio_value_history": {
            method: histories[method] for method in METHODS
        },
    }
    result["expanded_metrics"] = compute_expanded_metrics(
        records, histories, table_by_method
    )
    return result


def main() -> None:
    args = parse_args()
    paths = [Path(value) for value in args.inputs]
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    for path, document in zip(paths, documents):
        document["metadata"]["source_result_files"] = [str(path)]
    result = merge_results(documents)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(result), encoding="utf-8")
    print("wrote %s" % output)
    print("wrote %s" % output.with_suffix(".md"))


if __name__ == "__main__":
    main()
