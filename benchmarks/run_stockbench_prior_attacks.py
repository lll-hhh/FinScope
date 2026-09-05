"""Run the K1-K4 public-prior attack experiment on StockBench traces.

The proxy audit log intentionally contains no raw prompt or local mapping. The
runner reconstructs only the information that an attacker is allowed to use:
the public catalog, public indicator cache, and the observable cross-round
alias/role pattern. It emits one flat row per (method, prior, trace length),
which can be consumed by ``finscope.adaptive.fit_risk_estimator``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from benchmarks.serve_privacy_proxy import stockbench_catalog


PRIOR_LEVELS = ("K1", "K2", "K3", "K4")
TRACE_LENGTHS = (1, 5, 20, 60, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--stockbench-root", required=True, type=Path)
    parser.add_argument("--methods", nargs="+", default=["global_alias", "episode_alias", "finscope"])
    parser.add_argument("--trace-lengths", nargs="+", type=int, default=list(TRACE_LENGTHS))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260905)
    return parser.parse_args()


def read_audit(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: audit row must be an object")
        if value.get("status") == "ok":
            rows.append(value)
    return rows


def day_key(row: Mapping[str, Any]) -> str:
    return str(row.get("trading_day") or row.get("date") or row.get("episode_id") or "")


def sort_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (day_key(row), int(row.get("request_id", 0)), str(row.get("role", ""))),
    )


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def indicator_signature(root: Path, symbol: str, day: str) -> Tuple[Tuple[str, str], ...]:
    path = root / "storage" / "cache" / "stock_indicators" / f"{symbol}_{day}.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, Mapping):
        return ()
    values: List[Tuple[str, str]] = []
    for key in ("market_cap", "pe_ratio", "dividend_yield", "week_52_high", "week_52_low", "quarterly_dividend"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            # Quantization models what an attacker can compare after observing
            # rounded public values, rather than granting exact real numbers.
            values.append((key, f"{float(value):.3g}"))
    return tuple(values)


def stable_tie(seed: int, alias: str, candidate: str) -> float:
    digest = hashlib.sha256(f"{seed}:{alias}:{candidate}".encode()).hexdigest()
    return int(digest[:12], 16) / float(16**12)


def jaccard(left: Sequence[Tuple[str, str]], right: Sequence[Tuple[str, str]]) -> float:
    a, b = set(left), set(right)
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def roc_auc(positives: Sequence[float], negatives: Sequence[float]) -> float:
    if not positives or not negatives:
        return 0.5
    labelled = sorted([(value, 1) for value in positives] + [(value, 0) for value in negatives])
    rank_sum = 0.0
    rank = 1
    index = 0
    while index < len(labelled):
        end = index + 1
        while end < len(labelled) and labelled[end][0] == labelled[index][0]:
            end += 1
        average_rank = (rank + rank + end - index - 1) / 2.0
        rank_sum += average_rank * sum(label for _, label in labelled[index:end])
        rank += end - index
        index = end
    p, n = len(positives), len(negatives)
    return (rank_sum - p * (p + 1) / 2.0) / (p * n)


def binding_features(
    binding: Mapping[str, Any],
    *,
    prior: str,
    day: str,
    root: Path,
    catalog: Mapping[str, Mapping[str, Any]],
    behavior: Mapping[str, Sequence[Tuple[str, str]]],
) -> List[Tuple[str, str]]:
    canonical = str(binding.get("canonical_id", ""))
    entry = catalog.get(canonical, {})
    result: List[Tuple[str, str]] = [("type", normalize(binding.get("entity_type", "stock")))]
    if prior in {"K2", "K3", "K4"}:
        result.extend(
            [
                ("descriptor", normalize(binding.get("descriptor", entry.get("descriptor", "")))),
                ("sector", normalize(entry.get("sector", ""))),
            ]
        )
    if prior in {"K3", "K4"}:
        result.extend(("indicator:" + key, value) for key, value in indicator_signature(root, canonical, day))
    if prior == "K4":
        result.extend(("behavior:" + key, value) for key, value in behavior.get(canonical, ()))
    return result


def attack_reid(
    rows: Sequence[Mapping[str, Any]],
    *,
    prior: str,
    root: Path,
    catalog: Mapping[str, Mapping[str, Any]],
    behavior: Mapping[str, Sequence[Tuple[str, str]]],
    seed: int,
) -> Tuple[float, int]:
    candidates = tuple(catalog)
    hits = 0
    queries = 0
    for row in rows:
        day = day_key(row)
        for binding in row.get("bindings", ()):
            if not isinstance(binding, Mapping):
                continue
            target = str(binding.get("canonical_id", ""))
            observed = binding_features(binding, prior=prior, day=day, root=root, catalog=catalog, behavior=behavior)
            scored = []
            for candidate in candidates:
                candidate_binding = {
                    "canonical_id": candidate,
                    "entity_type": catalog[candidate].get("entity_type", "stock"),
                    "descriptor": catalog[candidate].get("descriptor", ""),
                }
                expected = binding_features(candidate_binding, prior=prior, day=day, root=root, catalog=catalog, behavior=behavior)
                score = jaccard(observed, expected)
                scored.append((score, stable_tie(seed, str(binding.get("alias", "")), candidate), candidate))
            scored.sort(reverse=True)
            hits += int(scored and scored[0][2] == target)
            queries += len(candidates)
    return (hits / sum(1 for row in rows for item in row.get("bindings", ()) if isinstance(item, Mapping)) if any(row.get("bindings") for row in rows) else 0.0, queries)


def link_score(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    prior: str,
    root: Path,
    catalog: Mapping[str, Mapping[str, Any]],
    behavior: Mapping[str, Sequence[Tuple[str, str]]],
) -> float:
    left_binding = left.get("_binding", {})
    right_binding = right.get("_binding", {})
    left_features = binding_features(left_binding, prior=prior, day=day_key(left), root=root, catalog=catalog, behavior=behavior)
    right_features = binding_features(right_binding, prior=prior, day=day_key(right), root=root, catalog=catalog, behavior=behavior)
    score = jaccard(left_features, right_features)
    if prior == "K4" and left_binding.get("alias") and left_binding.get("alias") == right_binding.get("alias"):
        score += 1.0
    return score


def attack_link(
    rows: Sequence[Mapping[str, Any]],
    *,
    prior: str,
    root: Path,
    catalog: Mapping[str, Mapping[str, Any]],
    behavior: Mapping[str, Sequence[Tuple[str, str]]],
) -> float:
    by_day: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[day_key(row)].append(row)
    days = sorted(by_day)
    positives: List[float] = []
    negatives: List[float] = []
    for previous_day, current_day in zip(days, days[1:]):
        previous = by_day[previous_day]
        current = by_day[current_day]
        for left in previous:
            for right in current:
                left_bindings = [item for item in left.get("bindings", ()) if isinstance(item, Mapping)]
                right_bindings = [item for item in right.get("bindings", ()) if isinstance(item, Mapping)]
                if not left_bindings or not right_bindings:
                    continue
                # Each pair of observed bindings is one linkage decision. A
                # row-level score would make a daily request containing the
                # whole candidate pool look positive even for different
                # securities.
                for left_binding in left_bindings:
                    for right_binding in right_bindings:
                        left_view = dict(left)
                        right_view = dict(right)
                        left_view["_binding"] = left_binding
                        right_view["_binding"] = right_binding
                        score = link_score(left_view, right_view, prior=prior, root=root, catalog=catalog, behavior=behavior)
                        same = str(left_binding.get("canonical_id")) == str(right_binding.get("canonical_id"))
                        (positives if same else negatives).append(score)
    return roc_auc(positives, negatives)


def exposure_state(rows: Sequence[Mapping[str, Any]], trace_days: int) -> Dict[str, Any]:
    bindings = [item for row in rows for item in row.get("bindings", ()) if isinstance(item, Mapping)]
    roles = {str(row.get("role", "")) for row in rows if row.get("role")}
    assets = {str(item.get("canonical_id", "")) for item in bindings if item.get("canonical_id")}
    trade_events = sum(1 for row in rows if any(token in str(row.get("role", "")).casefold() for token in ("trade", "order", "execution")))
    return {
        "alias_occurrences": len(bindings),
        "age_days": max(0, trace_days - 1),
        "visible_roles": sorted(roles),
        "market_events": len(rows),
        "trade_events": trade_events,
        "distinct_assets": sorted(assets),
        "high_risk_events": sum(int(row.get("outbound_sensitive", 0) > 0) for row in rows),
    }


def evaluate(args: argparse.Namespace) -> Dict[str, Any]:
    catalog_entries = stockbench_catalog()
    catalog = {
        item.canonical_id: {
            "descriptor": item.descriptor,
            "sector": item.sector,
            "entity_type": item.entity_type,
        }
        for item in catalog_entries
    }
    output_rows: List[Dict[str, Any]] = []
    for method in args.methods:
        source_method = method
        rows = sort_rows(read_audit(args.audit_dir / f"stockbench_{source_method}_audit.jsonl"))
        # The external benchmark calls the fixed-lifetime baseline
        # ``global_alias``; accept ``fixed_alias`` as the table-facing name.
        if not rows and method == "fixed_alias":
            source_method = "global_alias"
            rows = sort_rows(read_audit(args.audit_dir / "stockbench_global_alias_audit.jsonl"))
        if not rows:
            raise FileNotFoundError(
                f"no successful StockBench audit rows for method {method!r} in {args.audit_dir}"
            )
        days = sorted({day_key(row) for row in rows})
        behavior: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for row in rows:
            for binding in row.get("bindings", ()):
                if isinstance(binding, Mapping) and binding.get("canonical_id"):
                    behavior[str(binding["canonical_id"])].append(("role", normalize(row.get("role", ""))))
        behavior = {key: tuple(sorted(set(value))) for key, value in behavior.items()}
        for prior in PRIOR_LEVELS:
            for requested_length in args.trace_lengths:
                length = len(days) if requested_length == 0 else requested_length
                selected_days = set(days[:length])
                trace = [row for row in rows if day_key(row) in selected_days]
                reid, queries = attack_reid(trace, prior=prior, root=args.stockbench_root, catalog=catalog, behavior=behavior, seed=args.seed)
                link = attack_link(trace, prior=prior, root=args.stockbench_root, catalog=catalog, behavior=behavior)
                state = exposure_state(trace, len(selected_days))
                output_rows.append({
                    "benchmark": "StockBench",
                    "model": "from_audit_log",
                    "method": method,
                    "prior_level": prior,
                    "trace_length": "full" if requested_length == 0 else requested_length,
                    "candidate_count": len(catalog),
                    "random_reid_at_1": 1 / len(catalog) if catalog else 0.0,
                    "reid_at_1": reid,
                    "link_auc": link,
                    "attack_queries": queries,
                    "observed_days": len(selected_days),
                    "observed_requests": len(trace),
                    "exposure_state": state,
                })
    return {
        "schema_version": 1,
        "metadata": {
            "benchmark": "StockBench",
            "attacker": "public-prior matcher; no local mappings or raw prompts",
            "priors": {
                "K1": "public security master only",
                "K2": "K1 + static sector and descriptor",
                "K3": "K2 + public historical indicators",
                "K4": "K3 + cross-round role and alias behavior",
            },
            "trace_lengths": ["1", "5", "20", "60", "full"],
        },
        "rows": output_rows,
    }


def main() -> None:
    args = parse_args()
    result = evaluate(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({len(result['rows'])} rows)")


if __name__ == "__main__":
    main()
