"""Paired circular moving-block bootstrap for merged NLPCC finance results."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import statistics
from typing import Dict, List, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--block-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def daily_returns(values: Sequence[float]) -> List[float]:
    return [values[index] / values[index - 1] - 1 for index in range(1, len(values))]


def metrics(returns: Sequence[float]) -> Tuple[float, float]:
    total = math.prod(1 + value for value in returns) - 1
    sharpe = (
        statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252)
        if len(returns) > 1 and statistics.stdev(returns) > 0
        else 0.0
    )
    return total, sharpe


def interval(values: Sequence[float]) -> List[float]:
    ordered = sorted(values)
    return [
        ordered[math.floor(0.025 * (len(ordered) - 1))],
        ordered[math.ceil(0.975 * (len(ordered) - 1))],
    ]


def evaluate(
    histories: Dict[str, Sequence[float]], replicates: int, block_size: int, seed: int
) -> Dict[str, object]:
    returns = {method: daily_returns(values) for method, values in histories.items()}
    lengths = {len(values) for values in returns.values()}
    if len(lengths) != 1:
        raise ValueError("all methods must contain the same number of daily returns")
    periods = lengths.pop()
    block = max(1, min(block_size, periods))
    rng = random.Random(seed)
    bootstraps = {
        method: {"return": [], "sharpe": [], "return_delta": [], "sharpe_delta": []}
        for method in returns
    }
    for _ in range(replicates):
        indices: List[int] = []
        while len(indices) < periods:
            start = rng.randrange(periods)
            indices.extend((start + offset) % periods for offset in range(block))
        indices = indices[:periods]
        sampled = {
            method: metrics([values[index] for index in indices])
            for method, values in returns.items()
        }
        vanilla_return, vanilla_sharpe = sampled["vanilla"]
        for method, (total_return, sharpe) in sampled.items():
            target = bootstraps[method]
            target["return"].append(total_return)
            target["sharpe"].append(sharpe)
            target["return_delta"].append(total_return - vanilla_return)
            target["sharpe_delta"].append(sharpe - vanilla_sharpe)
    result = {}
    for method, values in returns.items():
        total_return, sharpe = metrics(values)
        result[method] = {
            "total_return": total_return,
            "total_return_95ci": interval(bootstraps[method]["return"]),
            "sharpe": sharpe,
            "sharpe_95ci": interval(bootstraps[method]["sharpe"]),
            "total_return_delta_vs_vanilla_95ci": interval(
                bootstraps[method]["return_delta"]
            ),
            "sharpe_delta_vs_vanilla_95ci": interval(
                bootstraps[method]["sharpe_delta"]
            ),
        }
    return {
        "metadata": {
            "method": "paired circular moving-block bootstrap",
            "replicates": replicates,
            "block_size": block,
            "seed": seed,
            "periods": periods,
        },
        "metrics": result,
    }


def main() -> None:
    args = parse_args()
    source = Path(args.input)
    document = json.loads(source.read_text(encoding="utf-8"))
    result = evaluate(
        document["portfolio_value_history"],
        args.replicates,
        args.block_size,
        args.seed,
    )
    result["metadata"]["source_result"] = str(source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
