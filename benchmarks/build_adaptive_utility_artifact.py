"""Build the development utility table used for adaptive-threshold selection.

The reference run is the no-rotation Episode Alias policy. Candidate runs are
FinScope replays at different T values on the same development interval. The
script records each native StockBench metric loss separately and exposes the
maximum constrained loss to ``calibrate_adaptive_policy``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


def metric(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_rate(path: Path) -> float:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("status") == "ok":
                rows.append(row)
    if not rows:
        return 0.0
    return sum(bool(row.get("exact_restore", True)) for row in rows) / len(rows)


def successful_requests(path: Path) -> tuple[int, int]:
    total = 0
    successful = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        row = json.loads(line)
        successful += row.get("status") == "ok"
    return successful, total


def locate(report_root: Path, run_id: str) -> Path:
    matches = sorted(report_root.glob(run_id + "_*/metrics.json"))
    if not matches:
        raise FileNotFoundError(f"no metrics.json found for run id {run_id!r}")
    return matches[-1]


def attack_summary(path: Path) -> tuple[float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, Mapping) else payload
    candidates = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("method", "")) == "finscope"
        and str(row.get("prior_level", "")) == "K4"
        and str(row.get("trace_length", "")) in {"full", "0"}
    ]
    if not candidates:
        candidates = [row for row in rows if isinstance(row, Mapping)]
    if not candidates:
        raise ValueError(f"attack artifact has no rows: {path}")
    row = candidates[-1]
    return float(row.get("reid_at_1", row.get("reid", 1.0))), float(row.get("link_auc", 1.0))


def loss_up(reference: float, candidate: float, scale: float) -> float:
    return max(0.0, (reference - candidate) / max(scale, 1e-6))


def loss_down(reference: float, candidate: float, scale: float) -> float:
    return max(0.0, (reference - candidate) / max(scale, 1e-6))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--reference-run-id", required=True)
    parser.add_argument("--reference-audit", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, metavar="T:RUN_ID:AUDIT")
    parser.add_argument("--candidate-attack", action="append", default=[], metavar="T:ATTACK_JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-utility-loss", type=float, default=0.05)
    parser.add_argument("--min-valid", type=float, default=0.80)
    parser.add_argument("--min-trades", type=int, default=1)
    parser.add_argument("--min-trade-ratio", type=float, default=0.50)
    args = parser.parse_args()

    ref_path = locate(args.report_root, args.reference_run_id)
    ref = metric(ref_path)
    ref_valid = valid_rate(args.reference_audit)
    ref_successful, ref_requests = successful_requests(args.reference_audit)
    ref_execution_success = ref_successful / ref_requests if ref_requests else 0.0
    ref_trades = int(ref.get("trades_count", 0))
    attack_by_threshold = {}
    for spec in args.candidate_attack:
        threshold_text, attack_path = spec.split(":", 1)
        attack_by_threshold[float(threshold_text)] = attack_summary(Path(attack_path))
    rows = []
    for spec in args.candidate:
        try:
            threshold_text, run_id, audit_text = spec.split(":", 2)
            threshold = float(threshold_text)
        except ValueError as exc:
            raise ValueError(f"invalid --candidate {spec!r}; expected T:RUN_ID:AUDIT") from exc
        path = locate(args.report_root, run_id)
        candidate = metric(path)
        candidate_audit = Path(audit_text)
        candidate_valid = valid_rate(candidate_audit)
        candidate_successful, candidate_requests = successful_requests(candidate_audit)
        candidate_execution_success = (
            candidate_successful / candidate_requests if candidate_requests else 0.0
        )
        candidate_trades = int(candidate.get("trades_count", 0))
        reid_at_1, link_auc = attack_by_threshold.get(threshold, (1.0, 1.0))
        losses = {
            "return": loss_up(
                float(ref.get("cum_return", 0.0)),
                float(candidate.get("cum_return", 0.0)),
                max(abs(float(ref.get("cum_return", 0.0))), 0.01),
            ),
            "sharpe": loss_up(
                float(ref.get("sharpe", 0.0)),
                float(candidate.get("sharpe", 0.0)),
                max(abs(float(ref.get("sharpe", 0.0))), 1.0),
            ),
            # MDD is negative; a more negative candidate is a degradation.
            "mdd": loss_down(
                float(ref.get("max_drawdown", 0.0)),
                float(candidate.get("max_drawdown", 0.0)),
                max(abs(float(ref.get("max_drawdown", 0.0))), 0.01),
            ),
            "valid": max(0.0, ref_valid - candidate_valid),
            "execution_success": max(
                0.0, ref_execution_success - candidate_execution_success
            ),
        }
        disqualification_reasons = []
        required_trades = max(
            args.min_trades,
            int(ref_trades * args.min_trade_ratio + 0.999999),
        )
        if candidate_trades < required_trades:
            disqualification_reasons.append(
                f"trades_count={candidate_trades} below required {required_trades}"
            )
        if candidate_valid < args.min_valid:
            disqualification_reasons.append(
                f"valid={candidate_valid:.6f} below required {args.min_valid:.6f}"
            )
        if candidate_execution_success < args.min_valid:
            disqualification_reasons.append(
                "execution_success=%.6f below required %.6f"
                % (candidate_execution_success, args.min_valid)
            )
        non_degenerate = not disqualification_reasons
        rows.append(
            {
                "threshold": threshold,
                "utility_loss": max(losses.values()),
                "non_degenerate": non_degenerate,
                "eligible": non_degenerate and max(losses.values()) <= args.max_utility_loss,
                "disqualification_reasons": disqualification_reasons,
                "reid_at_1": reid_at_1,
                "link_auc": link_auc,
                "metric_losses": losses,
                "reference": {
                    "run_id": args.reference_run_id,
                    "metrics": dict(ref),
                    "valid": ref_valid,
                    "execution_success": ref_execution_success,
                },
                "candidate": {
                    "run_id": run_id,
                    "metrics": dict(candidate),
                    "valid": candidate_valid,
                    "execution_success": candidate_execution_success,
                },
            }
        )
    rows.sort(key=lambda row: row["threshold"])
    payload = {
        "schema_version": 1,
        "protocol": "development-only utility replay against Episode Alias reference",
        "max_utility_loss": args.max_utility_loss,
        "non_degeneracy": {
            "min_valid": args.min_valid,
            "min_trades": args.min_trades,
            "min_trade_ratio_vs_reference": args.min_trade_ratio,
            "reference_trades": ref_trades,
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({len(rows)} candidate rows)")


if __name__ == "__main__":
    main()
