"""Aggregate StockBench and FinVault native, privacy, recovery and cost metrics."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from benchmarks.serve_privacy_proxy import (
    CatalogEntry,
    finvault_catalog,
    stockbench_catalog,
)
from finscope.privacy_agent import AssetProfile, DeterministicDisclosurePlanner


METHODS = (
    "vanilla",
    "deletion",
    "llm_rewrite",
    "global_alias",
    "episode_alias",
    "finscope",
)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: audit row must be an object")
        rows.append(value)
    return rows


def usage_total(usage: Any) -> int:
    return int(usage.get("total_tokens", 0)) if isinstance(usage, Mapping) else 0


def summarize_audit(path: Path) -> Dict[str, Any] | None:
    rows = read_jsonl(path)
    if not rows:
        return None
    successful = [row for row in rows if row.get("status") == "ok"]
    restoration = [row for row in successful if row.get("exact_restore") is not None]
    return {
        "requests": len(rows),
        "successful_requests": len(successful),
        "request_success_rate": len(successful) / len(rows),
        "input_sensitive_mentions": sum(int(row.get("input_sensitive", 0)) for row in rows),
        "outbound_sensitive_mentions": sum(int(row.get("outbound_sensitive", 0)) for row in rows),
        "rewrite_outbound_sensitive_mentions": sum(
            int((row.get("rewrite") or {}).get("outbound_sensitive", 0)) for row in rows
        ),
        "all_external_sensitive_mentions": sum(
            int(row.get("outbound_sensitive", 0))
            + int((row.get("rewrite") or {}).get("outbound_sensitive", 0))
            for row in rows
        ),
        "upstream_sensitive_mentions": sum(int(row.get("upstream_sensitive", 0)) for row in rows),
        "task_tokens": sum(usage_total(row.get("task_usage")) for row in successful),
        "rewrite_tokens": sum(
            usage_total((row.get("rewrite") or {}).get("usage")) for row in successful
        ),
        "total_tokens": sum(
            usage_total(row.get("task_usage"))
            + usage_total((row.get("rewrite") or {}).get("usage"))
            for row in successful
        ),
        "e2e_p95_ms": percentile(
            [row["total_latency_ms"] for row in successful if "total_latency_ms" in row],
            0.95,
        ),
        "exact_restore_rate": (
            sum(bool(row.get("exact_restore")) for row in restoration) / len(restoration)
            if restoration
            else None
        ),
        "unsafe_repair_rate": (
            sum(bool(row.get("unsafe_repair")) for row in successful) / len(successful)
            if successful
            else None
        ),
        "restoration_status": dict(Counter(row.get("restoration_status") for row in restoration)),
        "restoration_issue_codes": dict(
            Counter(
                issue.get("code")
                for row in restoration
                for issue in row.get("restoration_issues", [])
                if isinstance(issue, Mapping) and issue.get("code")
            )
        ),
    }


def summarize_stockbench_vanilla_cache(stockbench_root: Path) -> Dict[str, Any] | None:
    base = (
        stockbench_root
        / "storage/cache/llm/by_run/qwen38_vanilla_full_20250301_20250731"
    )
    if not base.is_dir():
        return None
    tokens: List[int] = []
    latencies: List[float] = []
    for path in base.rglob("*.json"):
        if path.name == "_index.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw = ((payload.get("output") or {}).get("raw_response") or {})
        if not isinstance(raw, Mapping):
            continue
        tokens.append(usage_total(raw.get("usage")))
        fingerprint = str(raw.get("system_fingerprint", ""))
        match = re.search(r"-([0-9]+(?:\.[0-9]+)?)s$", fingerprint)
        if match:
            latencies.append(float(match.group(1)) * 1000)
    if not tokens:
        return None
    return {
        "requests": len(tokens),
        "successful_requests": len(tokens),
        "request_success_rate": 1.0,
        "task_tokens": sum(tokens),
        "rewrite_tokens": 0,
        "total_tokens": sum(tokens),
        "e2e_p95_ms": percentile(latencies, 0.95),
        "exact_restore_rate": None,
        "unsafe_repair_rate": 0.0,
        "source": "StockBench enhanced LLM cache",
    }


def p3_descriptor(entry: CatalogEntry) -> str:
    profile = AssetProfile.from_catalog_entry(entry.as_finscope(), 0)
    return DeterministicDisclosurePlanner().plan(profile).at("P3").descriptor


def grouped_link_auc(group_sizes: Iterable[int], total: int) -> float:
    if total < 2:
        return 1.0
    same_group_negative = sum(size * (size - 1) for size in group_sizes)
    probability_tied_negative = same_group_negative / (total * (total - 1))
    return 1.0 - 0.5 * probability_tied_negative


def catalog_privacy_attack(
    entries: Sequence[CatalogEntry], method: str
) -> Dict[str, Any]:
    total = len(entries)
    if not total:
        raise ValueError("privacy attack requires a non-empty public candidate catalog")
    if method == "vanilla":
        groups = [entry.canonical_id for entry in entries]
        link_auc = 1.0
    elif method == "deletion":
        groups = [entry.entity_type for entry in entries]
        sizes = Counter(groups)
        link_auc = grouped_link_auc(sizes.values(), total)
    elif method == "llm_rewrite":
        groups = [entry.descriptor for entry in entries]
        sizes = Counter(groups)
        link_auc = grouped_link_auc(sizes.values(), total)
    elif method == "global_alias":
        groups = ["opaque"] * total
        link_auc = 1.0
    elif method == "episode_alias":
        groups = ["opaque"] * total
        link_auc = 0.5
    elif method == "finscope":
        groups = [p3_descriptor(entry) for entry in entries]
        sizes = Counter(groups)
        link_auc = grouped_link_auc(sizes.values(), total)
    else:
        raise ValueError(f"unknown method: {method}")
    sizes = Counter(groups)
    return {
        "attacker": "catalog_side_information_oracle_random_tie_break",
        "candidate_count": total,
        "observable_groups": len(sizes),
        "reid_at_1": len(sizes) / total,
        "link_auc": link_auc,
        "identity_scope": "benchmark-local public identifiers",
    }


def latest_stock_metrics(stockbench_root: Path, method: str) -> Path | None:
    report_root = stockbench_root / "storage/reports/backtest"
    if method == "vanilla":
        patterns = (
            "qwen38_vanilla_full_20250301_20250731_*/metrics.json",
            "qwen38_vanilla_*_privacy_full_20250301_20250731_*/metrics.json",
        )
    else:
        patterns = (
            f"qwen38_{method}_full_20250303_20250731_*/metrics.json",
            f"qwen38_{method}_*_privacy_full_20250303_20250731_*/metrics.json",
        )
    paths = [path for pattern in patterns for path in report_root.glob(pattern)]
    return max(paths, key=lambda item: item.stat().st_mtime) if paths else None


def stock_native(path: Path | None) -> Dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        "total_return": value.get("cum_return"),
        "sortino_annual": value.get("sortino_annual"),
        "max_drawdown": abs(value.get("max_drawdown", 0.0)),
        "sharpe": value.get("sharpe"),
        "artifact": str(path),
    }


def iter_attack_cases(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    reports = payload.get("scenario_reports", {})
    if isinstance(reports, Mapping):
        reports = reports.values()
    for report in reports if isinstance(reports, Sequence) or hasattr(reports, "__iter__") else ():
        if not isinstance(report, Mapping):
            continue
        for case in report.get("case_results", []):
            if isinstance(case, Mapping):
                yield case


def finvault_native(attack_path: Path, normal_path: Path) -> Dict[str, Any] | None:
    if not attack_path.is_file() or not normal_path.is_file():
        return None
    attack = json.loads(attack_path.read_text(encoding="utf-8"))
    normal = json.loads(normal_path.read_text(encoding="utf-8"))
    cases = list(iter_attack_cases(attack))
    violation_free = sum(
        not case.get("violations") and not case.get("vulnerabilities_triggered")
        for case in cases
    )
    attack_summary = attack.get("overall_summary") or attack.get("attack_summary") or {}
    normal_summary = normal.get("summary") or {}
    return {
        "benign_success": normal_summary.get("benign_success_rate"),
        "attack_success": attack_summary.get("attack_success_rate"),
        "violation_free": violation_free / len(cases) if cases else None,
        "over_refusal": normal_summary.get("over_refusal_rate"),
        "attack_cases": len(cases),
        "normal_cases": normal_summary.get("total_cases"),
        "attack_artifact": str(attack_path),
        "normal_artifact": str(normal_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--stockbench-root", type=Path, required=True)
    parser.add_argument("--finvault-root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalogs = {
        "stockbench": stockbench_catalog(),
        "finvault": finvault_catalog(args.finvault_root),
    }
    rows: List[Dict[str, Any]] = []
    vanilla_cost = summarize_stockbench_vanilla_cache(args.stockbench_root)
    for benchmark in ("stockbench", "finvault"):
        for method in METHODS:
            audit = summarize_audit(args.run_root / f"{benchmark}_{method}_audit.jsonl")
            if benchmark == "stockbench" and method == "vanilla":
                audit = vanilla_cost
            if benchmark == "stockbench":
                native = stock_native(latest_stock_metrics(args.stockbench_root, method))
            else:
                native = finvault_native(
                    args.results_root / f"finvault_qwen38_{method}_attacks_final.json",
                    args.results_root / f"finvault_qwen38_{method}_normal_final.json",
                )
            rows.append(
                {
                    "benchmark": benchmark,
                    "model": "Qwen3.8-27B",
                    "method": method,
                    "complete": native is not None and audit is not None,
                    "native": native,
                    "privacy": catalog_privacy_attack(catalogs[benchmark], method),
                    "audit": audit,
                    "token_delta_vs_vanilla": None,
                }
            )
    for benchmark in ("stockbench", "finvault"):
        benchmark_rows = [row for row in rows if row["benchmark"] == benchmark]
        baseline = next(row for row in benchmark_rows if row["method"] == "vanilla")
        baseline_tokens = (baseline.get("audit") or {}).get("total_tokens")
        if not baseline_tokens:
            continue
        for row in benchmark_rows:
            audit = row.get("audit") or {}
            if row["complete"] and audit.get("total_tokens") is not None:
                row["token_delta_vs_vanilla"] = (
                    audit["total_tokens"] / baseline_tokens - 1.0
                )
    output = {
        "schema_version": 1,
        "rows": rows,
        "complete_rows": sum(row["complete"] for row in rows),
        "total_rows": len(rows),
        "notes": {
            "finvault_identity_scope": (
                "ReID targets public benchmark-local anonymized placeholders, not real people."
            ),
            "privacy_attacker": (
                "Fixed public-catalog side-information oracle with random tie breaking; "
                "the private restoration map is never provided to the attacker."
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"complete rows: {output['complete_rows']}/{output['total_rows']}")
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
