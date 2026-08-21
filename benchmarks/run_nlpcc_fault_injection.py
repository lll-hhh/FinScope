"""Run trace-driven restoration fault injection on a completed NLPCC result."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from benchmarks.run_nlpcc_real import (
    FUND_POOL,
    FUND_PROFILES,
    LocalPrivacyAgent,
    Portfolio,
    asset_catalog,
    execute_action,
    parse_action,
    prepare_outbound,
    restore_and_validate,
)


HANDLE = re.compile(
    r'<fin-ref type="asset" id="(?P<id>FS_ASSET_[A-F0-9]+)">(?P<description>.*?)</fin-ref>'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--level", default="P3", choices=("P1", "P2", "P3", "P4", "P5"))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def empty_payload(date: str) -> Dict[str, Any]:
    return {
        "date": date,
        "candidate_pool": [
            {
                "asset": asset,
                "name": FUND_PROFILES[asset][0],
                "category": FUND_PROFILES[asset][1],
                "prices": [],
            }
            for asset in FUND_POOL
        ],
        "news": [],
        "portfolio": {"cash": 100_000.0, "holdings": [], "total_value": 100_000.0},
    }


def canonical_action(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    action = record.get("restored_action")
    if not record.get("valid") or not isinstance(action, Mapping):
        return None
    asset = action.get("asset")
    side = action.get("action")
    if asset not in FUND_POOL or side not in {"buy", "sell", "hold"}:
        return None
    return dict(action)


def synthetic_portfolio(action: Mapping[str, Any]) -> Portfolio:
    portfolio = Portfolio()
    portfolio.holdings = {asset: 10_000.0 for asset in FUND_POOL}
    portfolio.cash = 100_000.0
    return portfolio


def run_variant(
    raw: str,
    scope: Any,
    agent: LocalPrivacyAgent,
    initial: Portfolio,
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str], Portfolio]:
    parsed = parse_action(raw)
    restored, valid, rejection = restore_and_validate(
        "finscope", parsed, scope, agent, {}
    )
    state = deepcopy(initial)
    if valid and restored is not None:
        executed, execution_rejection = execute_action(state, restored)
        if not executed:
            return restored, False, execution_rejection, state
    return restored, valid, rejection, state


def perturbations(
    outbound: Mapping[str, Any],
    representation: Mapping[str, str],
    previous: Optional[Mapping[str, str]],
    canonical: Mapping[str, Any],
) -> Dict[str, Tuple[str, bool]]:
    asset = str(canonical["asset"])
    clean = dict(canonical)
    clean["asset"] = representation[asset]
    clean_json = json.dumps(clean, ensure_ascii=False)
    current_handle = representation[asset]
    match = HANDLE.fullmatch(current_handle)
    if match is None:
        raise RuntimeError("unexpected FinScope handle surface")
    descriptor = match.group("description")
    other_asset = next(item for item in FUND_POOL if item != asset)
    variants: Dict[str, Tuple[str, bool]] = {
        "clean": (clean_json, False),
        "prefix_suffix_quotes_brackets": (
            "model answer:\n```json\n" + clean_json + "\n```\nend",
            False,
        ),
        "descriptor_without_handle": (
            json.dumps({**clean, "asset": descriptor}, ensure_ascii=False),
            True,
        ),
        "binding_descriptor_tamper": (
            json.dumps(
                {**clean, "asset": current_handle.replace(descriptor, descriptor + "篡改")},
                ensure_ascii=False,
            ),
            True,
        ),
        "truncated_handle": (
            json.dumps({**clean, "asset": current_handle.replace(match.group("id"), match.group("id")[:-2])}, ensure_ascii=False),
            True,
        ),
        "fabricated_handle": (
            json.dumps({**clean, "asset": current_handle.replace(match.group("id"), "FS_ASSET_DEADBEEF")}, ensure_ascii=False),
            True,
        ),
        "same_type_handle_swap": (
            json.dumps({**clean, "asset": representation[other_asset]}, ensure_ascii=False),
            True,
        ),
        "malformed_json": (clean_json[:-1], True),
    }
    if previous is not None:
        variants["stale_previous_day_handle"] = (
            json.dumps({**clean, "asset": previous[asset]}, ensure_ascii=False),
            True,
        )
    numeric = dict(clean)
    if canonical["action"] == "sell":
        numeric["percentage"] = 1.5
    else:
        numeric["action"] = "buy"
        numeric["amount"] = -1
    variants["numeric_out_of_range"] = (json.dumps(numeric, ensure_ascii=False), True)
    cash = dict(clean)
    cash["action"] = "buy"
    cash["amount"] = 1_000_000.0
    variants["execution_cash_violation"] = (json.dumps(cash, ensure_ascii=False), True)
    return variants


def evaluate(document: Mapping[str, Any], level: str) -> Dict[str, Any]:
    records = [
        record
        for record in document["daily_records"]
        if record.get("method") == "finscope" and canonical_action(record) is not None
    ]
    agent = LocalPrivacyAgent(asset_catalog(), default_level=level)
    fixed = {asset: f"FIXED_ASSET_{index:03d}" for index, asset in enumerate(FUND_POOL, 1)}
    totals: Dict[str, Dict[str, int]] = {}
    previous_representation: Optional[Mapping[str, str]] = None
    for record in records:
        canonical = canonical_action(record)
        assert canonical is not None
        date = str(record["date"])
        outbound, scope, representation, _ = prepare_outbound(
            "finscope",
            empty_payload(date),
            int(date.replace("-", "")),
            agent,
            fixed,
            level,
        )
        assert scope is not None
        initial = synthetic_portfolio(canonical)
        clean_raw = perturbations(
            outbound, representation, previous_representation, canonical
        )["clean"][0]
        clean_action, clean_valid, _, clean_state = run_variant(
            clean_raw, scope, agent, initial
        )
        if not clean_valid or clean_action != canonical:
            raise RuntimeError(f"clean action failed round trip on {date}")
        for name, (raw, should_reject) in perturbations(
            outbound, representation, previous_representation, canonical
        ).items():
            restored, accepted, _, state = run_variant(raw, scope, agent, initial)
            row = totals.setdefault(
                name,
                {
                    "cases": 0,
                    "exact_restore": 0,
                    "correct_reject": 0,
                    "unsafe_repair": 0,
                    "state_equivalent": 0,
                },
            )
            row["cases"] += 1
            row["exact_restore"] += bool(accepted and restored == canonical)
            row["correct_reject"] += bool(should_reject and not accepted)
            row["unsafe_repair"] += bool(accepted and restored != canonical)
            expected_state = initial if should_reject else clean_state
            row["state_equivalent"] += bool(asdict(state) == asdict(expected_state))
        previous_representation = dict(representation)
        agent.close_scope(scope)

    metrics = {}
    for name, counts in totals.items():
        cases = counts["cases"]
        metrics[name] = {
            **counts,
            "exact_restore_rate": counts["exact_restore"] / cases,
            "correct_reject_rate": counts["correct_reject"] / cases,
            "unsafe_repair_rate": counts["unsafe_repair"] / cases,
            "state_equivalence_rate": counts["state_equivalent"] / cases,
        }
    return {
        "metadata": {
            "benchmark": document["metadata"]["benchmark"],
            "source_model": document["metadata"]["model"],
            "source_model_revision": document["metadata"]["model_revision"],
            "source_finscope_commit": document["metadata"]["finscope_commit"],
            "source_valid_model_actions": len(records),
            "disclosure_level": level,
            "state_equivalence_reference": (
                "clean execution for accepted-format cases; unchanged pre-state for "
                "faults expected to be rejected"
            ),
        },
        "metrics": metrics,
    }


def main() -> None:
    args = parse_args()
    source = Path(args.input)
    document = json.loads(source.read_text(encoding="utf-8"))
    result = evaluate(document, args.level)
    result["metadata"]["source_result"] = str(source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
