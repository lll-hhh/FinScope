"""Benchmark adapters for the training-free LLM privacy attacker."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import random
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from benchmarks.llm_privacy_attacker import (
    AttackBatch,
    IdentityCandidate,
    IdentityTarget,
    LinkTarget,
)
from benchmarks.serve_privacy_proxy import CatalogEntry, finvault_catalog, stockbench_catalog


PRIOR_LEVELS = ("K1", "K2", "K3", "K4")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: expected an object")
        if value.get("status") == "ok":
            rows.append(value)
    return rows


def _day(row: Mapping[str, Any]) -> str:
    return str(row.get("trading_day") or row.get("date") or row.get("episode_id") or "")


def _sample_days(days: Sequence[str], maximum: int = 5) -> List[str]:
    if len(days) <= maximum:
        return list(days)
    indices = {round(index * (len(days) - 1) / (maximum - 1)) for index in range(maximum)}
    return [days[index] for index in sorted(indices)]


def _sample_values(values: Sequence[str], maximum: int) -> List[str]:
    """Keep evidence from the beginning, middle, and end of a long trace."""

    if len(values) <= maximum:
        return list(values)
    indices = {round(index * (len(values) - 1) / (maximum - 1)) for index in range(maximum)}
    return [values[index] for index in sorted(indices)]


def _indicator_profile(root: Path, symbol: str, day: str) -> Dict[str, float]:
    path = root / "storage" / "cache" / "stock_indicators" / f"{symbol}_{day}.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, Mapping):
        return {}
    result = {}
    for key in (
        "market_cap",
        "pe_ratio",
        "dividend_yield",
        "week_52_high",
        "week_52_low",
        "quarterly_dividend",
    ):
        item = value.get(key)
        if isinstance(item, (int, float)):
            result[key] = float(f"{float(item):.4g}")
    return result


def _candidate_profile(
    entry: CatalogEntry,
    prior: str,
    *,
    days: Sequence[str] = (),
    stockbench_root: Optional[Path] = None,
) -> Dict[str, Any]:
    profile: Dict[str, Any] = {"entity_type": entry.entity_type}
    if prior in {"K2", "K3", "K4"}:
        profile.update(
            {
                "name": entry.name,
                "sector": entry.sector,
                "description": entry.descriptor,
            }
        )
    if prior in {"K3", "K4"} and stockbench_root is not None:
        profile["public_indicators"] = {
            day: _indicator_profile(stockbench_root, entry.canonical_id, day)
            for day in _sample_days(days)
        }
    return profile


def _nlpcc_market_profiles(
    root: Path, assets: Sequence[str], days: Sequence[str]
) -> Dict[str, Dict[str, Any]]:
    """Load permitted K3 public history through the official NLPCC loader."""

    tasks_root = root / "repo" / "NLPCC_tasks"
    dataset_root = root / "lfs" / "NLPCC_tasks" / "dataset"
    if not tasks_root.is_dir() or not dataset_root.is_dir():
        raise FileNotFoundError(f"invalid NLPCC root for K3 prior: {root}")
    sys.path.insert(0, str(tasks_root))
    from dataset.dataloader_eval import DataLoader

    loader = DataLoader(
        str(dataset_root / "price_data" / "export_data"),
        str(dataset_root / "news_data" / "export_data"),
    )
    profiles: Dict[str, Dict[str, Any]] = {asset: {} for asset in assets}
    for day in _sample_days(days):
        date_value = int(day.replace("-", ""))
        history = loader.get_historical_prices(list(assets), date_value, 6)
        for asset in assets:
            rows = history.get(asset, [])
            if not rows:
                continue
            latest = rows[-1]
            public_values = {}
            for key in ("open", "close", "pct_change"):
                value = latest.get(key)
                if isinstance(value, (int, float)):
                    public_values[key] = float(f"{float(value):.5g}")
            if public_values:
                profiles[asset][day] = public_values
    return profiles


def _snippets(text: str, alias: str, *, radius: int = 220, maximum: int = 4) -> List[str]:
    values = []
    for match in re.finditer(re.escape(alias), text, flags=re.I):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        if snippet not in values:
            values.append(snippet)
        if len(values) >= maximum:
            break
    return values


def _binding_observation(
    *,
    alias: str,
    entity_type: str,
    days: Sequence[str],
    roles: Sequence[str],
    occurrences: int,
    disclosure_levels: Sequence[str],
    snippets: Sequence[str],
    prior: str,
) -> Dict[str, Any]:
    observation: Dict[str, Any] = {
        "protected_handle": alias,
        "entity_type": entity_type,
        "visible_context": list(snippets),
    }
    if prior == "K4":
        observation["cross_round_history"] = {
            "days": list(days),
            "roles": list(roles),
            "occurrences": occurrences,
            "disclosure_levels": list(disclosure_levels),
        }
    return observation


def _balanced_targets(
    values: Mapping[str, List[Tuple[str, Dict[str, Any]]]], maximum: int
) -> List[IdentityTarget]:
    selected: List[Tuple[str, str, Dict[str, Any]]] = []
    per_entity = max(1, maximum // max(1, len(values)))
    for truth in sorted(values):
        items = values[truth]
        if len(items) <= per_entity:
            chosen = items
        elif per_entity == 1:
            chosen = [items[-1]]
        else:
            chosen = [items[0], items[-1]][:per_entity]
        selected.extend((truth, alias, observation) for alias, observation in chosen)
    selected = selected[:maximum]
    return [
        IdentityTarget(f"target-{index:04d}", truth, observation)
        for index, (truth, _, observation) in enumerate(selected, 1)
    ]


def _link_targets(
    nodes: Sequence[Tuple[str, str, str, str, Dict[str, Any]]], maximum: int, seed: int
) -> List[LinkTarget]:
    by_truth: Dict[Tuple[str, str], List[Tuple[str, str, Dict[str, Any]]]] = defaultdict(list)
    for scope, step, alias, truth, observation in nodes:
        by_truth[(scope, truth)].append((step, alias, observation))
    positives: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for truth in sorted(by_truth):
        ordered = sorted(by_truth[truth], key=lambda item: (item[0], item[1]))
        for left, right in zip(ordered, ordered[1:]):
            if left[0] != right[0]:
                positives.append((left[2], right[2]))
    step_nodes: Dict[Tuple[str, str], List[Tuple[str, str, Dict[str, Any]]]] = defaultdict(list)
    for scope, step, alias, truth, observation in nodes:
        step_nodes[(scope, step)].append((truth, alias, observation))
    negatives: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    scopes = sorted({scope for scope, _ in step_nodes})
    for scope in scopes:
        steps = sorted(step for node_scope, step in step_nodes if node_scope == scope)
        for left_step, right_step in zip(steps, steps[1:]):
            right = sorted(step_nodes[(scope, right_step)])
            for index, (truth, _, left_observation) in enumerate(
                sorted(step_nodes[(scope, left_step)])
            ):
                alternatives = [item for item in right if item[0] != truth]
                if alternatives:
                    negatives.append(
                        (left_observation, alternatives[index % len(alternatives)][2])
                    )
    rng = random.Random(seed)
    each = maximum // 2
    rng.shuffle(positives)
    rng.shuffle(negatives)
    labelled = [(True, pair) for pair in positives[:each]] + [
        (False, pair) for pair in negatives[:each]
    ]
    rng.shuffle(labelled)
    return [
        LinkTarget(f"pair-{index:04d}", label, left, right)
        for index, (label, (left, right)) in enumerate(labelled, 1)
    ]


def stockbench_batches(
    *,
    audit_dir: Path,
    stockbench_root: Path,
    methods: Sequence[str],
    prior_levels: Sequence[str],
    trace_lengths: Sequence[int],
    max_identity_targets: int = 40,
    max_link_pairs: int = 80,
    seed: int = 20260906,
) -> Iterable[AttackBatch]:
    entries = stockbench_catalog()
    entry_by_id = {entry.canonical_id: entry for entry in entries}
    for method in methods:
        source = "global_alias" if method == "fixed_alias" else method
        rows = _read_jsonl(audit_dir / f"stockbench_{source}_audit.jsonl")
        rows = [
            row
            for row in rows
            if str(row.get("role", "")).casefold()
            not in {"backtest_report", "summary_report"}
        ]
        if not rows:
            raise FileNotFoundError(f"no StockBench audit rows for {method} in {audit_dir}")
        if not all(row.get("attacker_view") for row in rows):
            raise ValueError(
                f"StockBench audit for {method} has no exact attacker_view; "
                "rerun with the current privacy proxy"
            )
        all_days = sorted({_day(row) for row in rows})
        for requested_length in trace_lengths:
            selected_days = all_days if requested_length == 0 else all_days[:requested_length]
            selected_set = set(selected_days)
            trace = [row for row in rows if _day(row) in selected_set]
            for prior in prior_levels:
                handle_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
                day_nodes: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
                for row in trace:
                    day = _day(row)
                    view_text = json.dumps(row.get("attacker_view", {}), ensure_ascii=False)
                    for binding in row.get("bindings", []):
                        if not isinstance(binding, Mapping):
                            continue
                        truth = str(binding.get("canonical_id", ""))
                        alias = str(binding.get("alias", ""))
                        if truth not in entry_by_id or not alias:
                            continue
                        snippets = _snippets(view_text, alias)
                        if not snippets:
                            continue
                        key = (truth, alias)
                        state = handle_state.setdefault(
                            key,
                            {
                                "days": set(),
                                "roles": set(),
                                "occurrences": 0,
                                "levels": set(),
                                "snippets": [],
                                "descriptor": str(binding.get("descriptor", "")),
                                "entity_type": str(binding.get("entity_type", "stock")),
                            },
                        )
                        state["days"].add(day)
                        state["roles"].add(str(row.get("role", "")))
                        state["occurrences"] += max(1, view_text.casefold().count(alias.casefold()))
                        if binding.get("disclosure_level"):
                            state["levels"].add(str(binding["disclosure_level"]))
                        for snippet in snippets:
                            if snippet not in state["snippets"]:
                                state["snippets"].append(snippet)
                        node = day_nodes.setdefault(
                            (day, truth, alias),
                            {
                                "roles": set(),
                                "snippets": [],
                                "descriptor": state["descriptor"],
                                "entity_type": state["entity_type"],
                                "levels": set(),
                            },
                        )
                        node["roles"].add(str(row.get("role", "")))
                        node["levels"].update(state["levels"])
                        for snippet in snippets:
                            if snippet not in node["snippets"]:
                                node["snippets"].append(snippet)

                grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
                for (truth, alias), state in sorted(handle_state.items()):
                    days = sorted(state["days"])
                    observation = _binding_observation(
                        alias=alias,
                        entity_type=state["entity_type"],
                        days=days,
                        roles=sorted(state["roles"]),
                        occurrences=int(state["occurrences"]),
                        disclosure_levels=sorted(state["levels"]),
                        snippets=_sample_values(state["snippets"], 4),
                        prior=prior,
                    )
                    grouped[truth].append((alias, observation))

                link_nodes: List[Tuple[str, str, str, str, Dict[str, Any]]] = []
                for (day, truth, alias), state in sorted(day_nodes.items()):
                    link_nodes.append(
                        (
                            "stockbench",
                            day,
                            alias,
                            truth,
                            _binding_observation(
                                alias=alias,
                                entity_type=state["entity_type"],
                                days=[day],
                                roles=sorted(state["roles"]),
                                occurrences=1,
                                disclosure_levels=sorted(state["levels"]),
                                snippets=_sample_values(state["snippets"], 2),
                                prior=prior,
                            ),
                        )
                    )
                yield AttackBatch(
                    benchmark="StockBench",
                    method=method,
                    prior_level=prior,
                    trace_length="full" if requested_length == 0 else str(requested_length),
                    candidates=[
                        IdentityCandidate(
                            entry.canonical_id,
                            _candidate_profile(
                                entry,
                                prior,
                                days=selected_days,
                                stockbench_root=stockbench_root,
                            ),
                        )
                        for entry in entries
                    ],
                    identity_targets=_balanced_targets(grouped, max_identity_targets),
                    link_targets=(
                        _link_targets(link_nodes, max_link_pairs, seed)
                        if len(selected_days) > 1
                        else []
                    ),
                    exposure_state={
                        "alias_occurrences": sum(
                            int(state["occurrences"]) for state in handle_state.values()
                        ),
                        "age_days": max(0, len(selected_days) - 1),
                        "visible_roles": sorted(
                            {
                                str(row.get("role", ""))
                                for row in trace
                                if str(row.get("role", ""))
                            }
                        ),
                        "market_events": len(trace),
                        "trade_events": sum(
                            str(row.get("role", "")).casefold()
                            in {"execution", "trade_executor"}
                            for row in trace
                        ),
                        "distinct_assets": sorted(grouped),
                        "high_risk_events": sum(
                            int((row.get("adaptive") or {}).get("exposure_state", {}).get(
                                "high_risk_events", 0
                            ))
                            for row in trace[-1:]
                        ),
                    },
                )


def nlpcc_batches(
    *,
    result_path: Path,
    nlpcc_root: Path,
    methods: Sequence[str],
    prior_levels: Sequence[str],
    trace_lengths: Sequence[int],
    max_identity_targets: int = 40,
    max_link_pairs: int = 80,
    seed: int = 20260906,
) -> Iterable[AttackBatch]:
    from benchmarks.run_nlpcc_real import FUND_POOL, FUND_PROFILES

    document = json.loads(result_path.read_text(encoding="utf-8"))
    records = document.get("daily_records", [])
    if not any(isinstance(row, Mapping) and row.get("attacker_view") for row in records):
        raise ValueError("NLPCC result has no attacker_view; rerun with the current runner")
    entries = [
        CatalogEntry(asset, name, (), "financial asset", descriptor)
        for asset, (name, descriptor) in FUND_PROFILES.items()
    ]
    entry_by_id = {entry.canonical_id: entry for entry in entries}
    market_cache: Dict[Tuple[str, ...], Dict[str, Dict[str, Any]]] = {}
    for method in methods:
        method_rows = [row for row in records if row.get("method") == method]
        days = sorted({str(row.get("date", "")) for row in method_rows})
        for requested_length in trace_lengths:
            selected_days = days if requested_length == 0 else days[:requested_length]
            selected = [row for row in method_rows if str(row.get("date")) in set(selected_days)]
            market_key = tuple(selected_days)
            if market_key not in market_cache:
                market_cache[market_key] = _nlpcc_market_profiles(
                    nlpcc_root, FUND_POOL, selected_days
                )
            market_profiles = market_cache[market_key]
            for prior in prior_levels:
                grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
                nodes: List[Tuple[str, str, str, str, Dict[str, Any]]] = []
                for row in selected:
                    outbound = row.get("outbound_action") or {}
                    restored = row.get("restored_action") or {}
                    alias = str(outbound.get("asset", ""))
                    truth = str(restored.get("asset", ""))
                    if truth not in entry_by_id or not alias:
                        continue
                    view = row.get("attacker_view", {})
                    text = json.dumps(view, ensure_ascii=False)
                    observation: Dict[str, Any] = {
                        "protected_handle": alias,
                        "visible_context": _snippets(text, alias, radius=350),
                    }
                    if prior == "K4":
                        observation["cross_round_history"] = {
                            "day": row.get("date"),
                            "selected_action_visible": True,
                        }
                    grouped[truth].append((alias, observation))
                    nodes.append(
                        ("nlpcc", str(row.get("date", "")), alias, truth, observation)
                    )
                yield AttackBatch(
                    benchmark="NLPCC",
                    method=method,
                    prior_level=prior,
                    trace_length="full" if requested_length == 0 else str(requested_length),
                    candidates=[
                        IdentityCandidate(
                            entry.canonical_id,
                            {
                                **_candidate_profile(entry, prior),
                                **(
                                    {"public_market_history": market_profiles[entry.canonical_id]}
                                    if prior in {"K3", "K4"}
                                    else {}
                                ),
                            },
                        )
                        for entry in entries
                    ],
                    identity_targets=_balanced_targets(grouped, max_identity_targets),
                    link_targets=(
                        _link_targets(nodes, max_link_pairs, seed)
                        if len(selected_days) > 1
                        else []
                    ),
                    exposure_state={
                        "alias_occurrences": sum(
                            json.dumps(row.get("attacker_view", {}), ensure_ascii=False)
                            .casefold()
                            .count(str((row.get("outbound_action") or {}).get("asset", "")).casefold())
                            for row in selected
                            if (row.get("outbound_action") or {}).get("asset")
                        ),
                        "age_days": max(0, len(selected_days) - 1),
                        "visible_roles": ["portfolio_agent"],
                        "market_events": len(selected),
                        "trade_events": sum(bool(row.get("executed")) for row in selected),
                        "distinct_assets": sorted(grouped),
                        "high_risk_events": sum(not bool(row.get("valid")) for row in selected),
                    },
                )


def finvault_batches(
    *,
    audit_dir: Path,
    finvault_root: Path,
    methods: Sequence[str],
    prior_levels: Sequence[str],
    trace_lengths: Sequence[int],
    max_identity_targets: int = 30,
    max_link_pairs: int = 60,
    max_candidates: int = 100,
    seed: int = 20260906,
) -> Iterable[AttackBatch]:
    entries = finvault_catalog(finvault_root)
    entry_by_id = {entry.canonical_id: entry for entry in entries}
    for method in methods:
        source = "global_alias" if method == "fixed_alias" else method
        rows = _read_jsonl(audit_dir / f"finvault_{source}_audit.jsonl")
        if not rows:
            raise FileNotFoundError(f"no FinVault audit rows for {method} in {audit_dir}")
        if not any(row.get("attacker_view") for row in rows):
            raise ValueError("FinVault audit has no attacker_view; rerun with the current proxy")
        by_episode: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_episode[str(row.get("episode_id", ""))].append(row)
        for requested_length in trace_lengths:
            trace = []
            for episode_rows in by_episode.values():
                ordered = sorted(episode_rows, key=lambda row: int(row.get("request_id", 0)))
                trace.extend(ordered if requested_length == 0 else ordered[:requested_length])
            for prior in prior_levels:
                grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
                nodes: List[Tuple[str, str, str, str, Dict[str, Any]]] = []
                for row in trace:
                    text = json.dumps(row.get("attacker_view", {}), ensure_ascii=False)
                    for binding in row.get("bindings", []):
                        if not isinstance(binding, Mapping):
                            continue
                        alias = str(binding.get("alias", ""))
                        truth = str(binding.get("canonical_id", ""))
                        snippets = _snippets(text, alias, radius=300)
                        if not snippets or truth not in entry_by_id:
                            continue
                        observation = {
                            "protected_handle": alias,
                            "entity_type": entry_by_id[truth].entity_type,
                            "visible_context": snippets,
                        }
                        if prior == "K4":
                            observation["cross_round_history"] = {
                                "episode": row.get("episode_id"),
                                "turn": row.get("request_id"),
                                "role": row.get("role"),
                            }
                        grouped[truth].append((alias, observation))
                        episode = str(row.get("episode_id", ""))
                        try:
                            step = f"{int(row.get('request_id', 0)):08d}"
                        except (TypeError, ValueError):
                            step = str(row.get("request_id", ""))
                        nodes.append((episode, step, alias, truth, observation))
                targets = _balanced_targets(grouped, max_identity_targets)
                truth_ids = {target.truth_id for target in targets}
                candidate_entries = [entry_by_id[value] for value in sorted(truth_ids)]
                rng = random.Random(seed)
                distractors = [entry for entry in entries if entry.canonical_id not in truth_ids]
                rng.shuffle(distractors)
                candidate_entries.extend(distractors[: max(0, max_candidates - len(candidate_entries))])
                yield AttackBatch(
                    benchmark="FinVault",
                    method=method,
                    prior_level=prior,
                    trace_length="full" if requested_length == 0 else str(requested_length),
                    candidates=[
                        IdentityCandidate(entry.canonical_id, _candidate_profile(entry, prior))
                        for entry in candidate_entries
                    ],
                    identity_targets=targets,
                    link_targets=(
                        _link_targets(nodes, max_link_pairs, seed)
                        if requested_length != 1
                        else []
                    ),
                    exposure_state={
                        "alias_occurrences": sum(
                            len(item.observation.get("visible_context", ()))
                            for item in targets
                        ),
                        "age_days": max(0, requested_length - 1)
                        if requested_length
                        else max(0, max((len(value) for value in by_episode.values()), default=1) - 1),
                        "visible_roles": sorted(
                            {str(row.get("role", "")) for row in trace if row.get("role")}
                        ),
                        "market_events": len(trace),
                        "trade_events": sum(
                            str(row.get("role", "")).casefold() in {"execution", "tool"}
                            for row in trace
                        ),
                        "distinct_assets": sorted(grouped),
                        "high_risk_events": sum(
                            not bool(row.get("exact_restore", True)) for row in trace
                        ),
                    },
                )
