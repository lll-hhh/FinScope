#!/usr/bin/env python3
"""Summarize official NLPCC backtest outputs and privacy-proxy audit logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from math import sqrt
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Iterable, Optional


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _pick(mapping: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _quantile(values: list[float], probability: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _financial_metrics(result: dict[str, Any]) -> dict[str, Any]:
    # The official engine's portfolio_value_history is the source used for its
    # own final return.  It may contain duplicate entries for a date, so retain
    # the last observation for each date before computing daily statistics.
    # Daily after-trade snapshots are not suitable here because their holdings
    # values can precede the engine's final mark-to-market update.
    end_of_day: dict[str, float] = {}
    for row in result.get("portfolio_value_history", []):
        if row.get("date") and row.get("value") is not None:
            end_of_day[str(row["date"])] = float(row["value"])
    values = [end_of_day[day] for day in sorted(end_of_day)]
    returns = [current / previous - 1 for previous, current in zip(values, values[1:]) if previous]
    sharpe = None
    if len(returns) > 1 and stdev(returns) > 0:
        sharpe = sqrt(252) * mean(returns) / stdev(returns)
    max_drawdown = None
    max_drawdown_duration = 0
    if values:
        peak = values[0]
        drawdowns = []
        current_duration = 0
        for value in values:
            if value >= peak:
                peak = value
                current_duration = 0
            else:
                current_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_duration)
            drawdowns.append(value / peak - 1)
        max_drawdown = min(drawdowns)

    trade_results = [
        trade
        for decision in result.get("agent_decisions", [])
        for trade in decision.get("trade_results", [])
    ]
    executed = sum(bool(trade.get("success")) for trade in trade_results)
    rejection_reasons = Counter()
    for trade in trade_results:
        if trade.get("success"):
            continue
        reason = str(trade.get("reason") or "unknown")
        if reason.startswith("Insufficient capital"):
            reason = "Insufficient capital"
        rejection_reasons[reason] += 1
    annualized_return = _pick(result.get("performance", result), ["annualized_return", "annual_return"])
    annualized_volatility = stdev(returns) * sqrt(252) if len(returns) > 1 else None
    var_threshold = _quantile(returns, 0.05)
    cvar_tail = [value for value in returns if var_threshold is not None and value <= var_threshold]
    return {
        "decision_days": len(end_of_day),
        "days_with_submitted_trades": len(result.get("agent_decisions", [])),
        "sharpe_ratio_computed": sharpe,
        "max_drawdown_computed": max_drawdown,
        "daily_return_mean": mean(returns) if returns else None,
        "daily_return_std": stdev(returns) if len(returns) > 1 else None,
        "annualized_volatility_computed": annualized_volatility,
        "calmar_ratio_computed": (
            float(annualized_return) / abs(max_drawdown)
            if annualized_return is not None and max_drawdown not in (None, 0)
            else None
        ),
        "positive_day_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "var_95_loss": max(0.0, -var_threshold) if var_threshold is not None else None,
        "cvar_95_loss": -mean(cvar_tail) if cvar_tail else None,
        "best_day_return": max(returns) if returns else None,
        "worst_day_return": min(returns) if returns else None,
        "max_drawdown_duration_days": max_drawdown_duration,
        "trade_attempt_count": len(trade_results),
        "executed_trade_count": executed,
        "rejected_trade_count": len(trade_results) - executed,
        "execution_success_rate": executed / len(trade_results) if trade_results else None,
        "commission_total": sum(float(trade.get("commission", 0) or 0) for trade in trade_results),
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
    }


def summarize(result_path: Path, audit_path: Path) -> dict[str, Any]:
    result = _read_json(result_path)
    performance = result.get("performance", result)
    audit = _read_jsonl(audit_path)
    ok = [row for row in audit if row.get("status") == "ok"]
    latencies = [float(row["latency_s"]) for row in ok if row.get("latency_s") is not None]
    usage = [row.get("usage", {}) for row in ok]
    days = sorted({row.get("day") for row in ok if row.get("day")})
    roles = Counter(row.get("role", "unknown") for row in ok)
    input_sensitive = sum(int(row.get("input_sensitive_occurrences", 0)) for row in audit)
    outbound_sensitive = sum(int(row.get("outbound_sensitive_occurrences", 0)) for row in audit)
    summary = {
        "condition": audit_path.parent.name,
        "result_file": str(result_path),
        "audit_file": str(audit_path),
        "total_return": _pick(performance, ["total_return", "cumulative_return"]),
        "sharpe_ratio_official": _pick(performance, ["sharpe_ratio", "sharpe"]),
        "max_drawdown_official": _pick(performance, ["max_drawdown", "maximum_drawdown"]),
        "annualized_return": _pick(performance, ["annualized_return", "annual_return"]),
        "request_count": len(audit),
        "successful_request_count": len(ok),
        "error_count": len(audit) - len(ok),
        "observed_text_dates": len(days),
        "role_request_counts": dict(sorted(roles.items())),
        "mean_latency_s": mean(latencies) if latencies else None,
        "median_latency_s": median(latencies) if latencies else None,
        "p95_latency_s": _quantile(latencies, 0.95),
        "total_prompt_tokens": sum(int(item.get("prompt_tokens", 0)) for item in usage),
        "total_completion_tokens": sum(int(item.get("completion_tokens", 0)) for item in usage),
        "total_alias_occurrences": sum(int(row.get("alias_occurrences", 0)) for row in ok),
        "input_sensitive_occurrences": input_sensitive,
        "outbound_sensitive_occurrences": outbound_sensitive,
        "input_sensitive_record_count": sum(
            int(row.get("input_sensitive_occurrences", 0)) > 0 for row in audit
        ),
        "outbound_sensitive_record_count": sum(
            int(row.get("outbound_sensitive_occurrences", 0)) > 0 for row in audit
        ),
        "external_identifier_exposure_rate": (
            outbound_sensitive / input_sensitive if input_sensitive else None
        ),
    }
    summary.update(_financial_metrics(result))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = summarize(args.result, args.audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
