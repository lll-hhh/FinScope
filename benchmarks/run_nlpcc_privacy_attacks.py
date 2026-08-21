"""Run public-side-information privacy attacks on NLPCC candidate traces."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from benchmarks.run_nlpcc_real import (
    FUND_POOL,
    LocalPrivacyAgent,
    Portfolio,
    asset_catalog,
    build_episode_aliases,
    build_payload,
    coarsen_market_features,
    load_official_data,
    prepare_outbound,
)


ATTACK_METHODS = (
    "vanilla",
    "deletion",
    "llm_rewrite",
    "fixed_alias",
    "episode_alias",
    "finscope",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nlpcc-root", required=True)
    parser.add_argument("--start-date", default="2025-01-02")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--lookback-days", type=int, default=6)
    parser.add_argument("--top-rank", type=int, default=20)
    parser.add_argument("--pre-k-days", type=int, default=1)
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--levels", nargs="+", default=["P1", "P2", "P3", "P4", "P5"])
    parser.add_argument("--methods", nargs="+", choices=ATTACK_METHODS, default=list(ATTACK_METHODS))
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--block-size", type=int, default=10)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def candidate_signature(candidate: Mapping[str, Any]) -> str:
    observable = {
        key: value
        for key, value in candidate.items()
        if key not in {"asset", "name"}
    }
    return json.dumps(observable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def similarity_tokens(candidate: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                if child_key not in {"asset", "name", "date"}:
                    visit(child, str(child_key))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                visit(child, key)
        elif value is not None:
            tokens.add(f"{key}={value}")

    visit(candidate)
    return tokens


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def roc_auc(positives: Sequence[float], negatives: Sequence[float]) -> float:
    labelled = sorted(
        [(value, 1) for value in positives] + [(value, 0) for value in negatives],
        key=lambda item: item[0],
    )
    positive_rank_sum = 0.0
    rank = 1
    index = 0
    while index < len(labelled):
        end = index + 1
        while end < len(labelled) and labelled[end][0] == labelled[index][0]:
            end += 1
        average_rank = (rank + rank + end - index - 1) / 2
        positive_rank_sum += average_rank * sum(label for _, label in labelled[index:end])
        rank += end - index
        index = end
    positive_count = len(positives)
    negative_count = len(negatives)
    if not positive_count or not negative_count:
        return 0.5
    return (
        positive_rank_sum - positive_count * (positive_count + 1) / 2
    ) / (positive_count * negative_count)


def moving_block_interval(
    values: Sequence[float], replicates: int, block_size: int
) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(20260821)
    length = len(values)
    block = max(1, min(block_size, length))
    estimates = []
    for _ in range(replicates):
        sample: List[float] = []
        while len(sample) < length:
            start = rng.randrange(length)
            sample.extend(values[(start + offset) % length] for offset in range(block))
        estimates.append(statistics.mean(sample[:length]))
    estimates.sort()
    return (
        estimates[math.floor(0.025 * (len(estimates) - 1))],
        estimates[math.ceil(0.975 * (len(estimates) - 1))],
    )


def trace_for_method(
    method: str,
    raw_payload: Dict[str, Any],
    date: int,
    level: str,
    agent: LocalPrivacyAgent,
    fixed_aliases: Mapping[str, str],
) -> Dict[str, Mapping[str, Any]]:
    aliases = build_episode_aliases(date) if method in {"llm_rewrite", "episode_alias"} else fixed_aliases
    outbound, scope, representations, _ = prepare_outbound(
        method, raw_payload, date, agent, aliases, level
    )
    if method == "deletion":
        result = {
            asset: candidate
            for asset, candidate in zip(FUND_POOL, outbound["candidate_pool"])
        }
    else:
        inverse = {representation: asset for asset, representation in representations.items()}
        result = {
            inverse[str(candidate["asset"])]: candidate
            for candidate in outbound["candidate_pool"]
        }
    if scope is not None:
        agent.close_scope(scope)
    return result


def public_signatures(
    method: str, raw_payload: Mapping[str, Any], level: str
) -> Dict[str, str]:
    payload = coarsen_market_features(raw_payload, level) if method == "finscope" else raw_payload
    return {
        str(candidate["asset"]): candidate_signature(candidate)
        for candidate in payload["candidate_pool"]
    }


def evaluate(args: argparse.Namespace) -> Dict[str, Any]:
    loader, dates, files = load_official_data(args)
    fixed_aliases = {
        asset: f"FIXED_ASSET_{index:03d}"
        for index, asset in enumerate(FUND_POOL, start=1)
    }
    metrics: Dict[str, Any] = {}
    for level in args.levels:
        agent = LocalPrivacyAgent(asset_catalog(), default_level=level)
        traces: Dict[str, List[Dict[str, Mapping[str, Any]]]] = defaultdict(list)
        top1_by_day: Dict[str, List[float]] = defaultdict(list)
        top5_by_day: Dict[str, List[float]] = defaultdict(list)
        anonymity_by_method: Dict[str, List[float]] = defaultdict(list)
        for date in dates:
            raw = build_payload(loader, date, Portfolio(), args)
            raw["news"] = []
            for method in args.methods:
                trace = trace_for_method(
                    method, raw, date, level, agent, fixed_aliases
                )
                traces[method].append(trace)
                signature_to_assets: Dict[str, List[str]] = defaultdict(list)
                for asset, signature in public_signatures(method, raw, level).items():
                    signature_to_assets[signature].append(asset)
                day_top1 = []
                day_top5 = []
                for asset, candidate in trace.items():
                    matches = signature_to_assets[candidate_signature(candidate)]
                    if asset not in matches:
                        raise RuntimeError(f"ground truth absent from attack set: {method} {date} {asset}")
                    anonymity = len(matches)
                    anonymity_by_method[method].append(anonymity)
                    day_top1.append(1 / anonymity)
                    day_top5.append(min(1.0, 5 / anonymity))
                top1_by_day[method].append(statistics.mean(day_top1))
                top5_by_day[method].append(statistics.mean(day_top5))

        level_metrics = {}
        for method in args.methods:
            positive_scores = []
            negative_scores = []
            for previous, current in zip(traces[method], traces[method][1:]):
                previous_tokens = {
                    asset: similarity_tokens(candidate)
                    for asset, candidate in previous.items()
                }
                current_tokens = {
                    asset: similarity_tokens(candidate)
                    for asset, candidate in current.items()
                }
                for left_asset, left_tokens in previous_tokens.items():
                    for right_asset, right_tokens in current_tokens.items():
                        score = jaccard(left_tokens, right_tokens)
                        (positive_scores if left_asset == right_asset else negative_scores).append(score)
            top1_ci = moving_block_interval(
                top1_by_day[method], args.bootstrap_replicates, args.block_size
            )
            top5_ci = moving_block_interval(
                top5_by_day[method], args.bootstrap_replicates, args.block_size
            )
            level_metrics[method] = {
                "cases": len(dates) * len(FUND_POOL),
                "trading_days": len(dates),
                "candidate_pool_size": len(FUND_POOL),
                "reid_at_1": statistics.mean(top1_by_day[method]),
                "reid_at_1_moving_block_95ci": list(top1_ci),
                "reid_at_5": statistics.mean(top5_by_day[method]),
                "reid_at_5_moving_block_95ci": list(top5_ci),
                "mean_candidate_anonymity": statistics.mean(anonymity_by_method[method]),
                "minimum_candidate_anonymity": min(anonymity_by_method[method]),
                "adjacent_day_link_auc": roc_auc(positive_scores, negative_scores),
            }
        metrics[level] = level_metrics
    return {
        "metadata": {
            "benchmark": "NLPCC 2026 Track 1 public A-set",
            "attack": "public master-data and price attribute matching oracle",
            "side_information": "candidate attributes and public prices; no handles, positions, or local mappings",
            "random_reid_at_1": 1 / len(FUND_POOL),
            "random_reid_at_5": 5 / len(FUND_POOL),
            "random_link_auc": 0.5,
            "levels": list(args.levels),
            "methods": list(args.methods),
            "files": files,
        },
        "metrics": metrics,
    }


def main() -> None:
    args = parse_args()
    result = evaluate(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
