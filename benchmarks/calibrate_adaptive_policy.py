"""Calibrate FinScope's risk estimator and replacement threshold on development data.

The attack artifact supplies labelled exposure -> (ReID@1, Link AUC) examples.
The utility artifact is produced by replaying candidate thresholds on the
development split and must contain ``threshold`` and ``utility_loss``.  No
test-set metric is read by this script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from finscope import DevPolicyResult, calibrate_threshold, fit_risk_estimator


def _rows(path: Path) -> Sequence[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON list or an object with rows")
    return [row for row in rows if isinstance(row, Mapping)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-artifact", required=True, type=Path)
    parser.add_argument("--utility-artifact", required=True, type=Path)
    parser.add_argument("--max-utility-loss", required=True, type=float)
    parser.add_argument(
        "--estimator-method",
        default="finscope",
        help="method whose attack rows train the online risk estimator (default: finscope)",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    attack_rows = list(_rows(args.attack_artifact))
    utility_rows = list(_rows(args.utility_artifact))
    if not attack_rows:
        raise ValueError("attack artifact has no rows")
    estimator_method = str(args.estimator_method).strip()
    estimator_rows = (
        [row for row in attack_rows if str(row.get("method", "")) == estimator_method]
        if estimator_method
        else attack_rows
    )
    if not estimator_rows:
        raise ValueError(
            "attack artifact has no rows for estimator method %r" % estimator_method
        )
    candidates = []
    for row in utility_rows:
        if "threshold" not in row or "utility_loss" not in row:
            raise ValueError("each utility row needs threshold and utility_loss")
        candidates.append(
            DevPolicyResult(
                float(row["threshold"]),
                float(row["utility_loss"]),
                float(row.get("reid_at_1", row.get("reid", 1.0))),
                float(row.get("link_auc", 1.0)),
            )
        )
    threshold = calibrate_threshold(candidates, max_utility_loss=args.max_utility_loss)
    estimator = fit_risk_estimator(estimator_rows)
    selected = min(
        (item for item in candidates if item.utility_loss <= args.max_utility_loss),
        key=lambda item: (item.privacy_risk, item.threshold),
    )
    result: Dict[str, Any] = {
        "schema_version": 1,
        "threshold": threshold,
        "max_utility_loss": args.max_utility_loss,
        "selected_development_policy": {
            "threshold": selected.threshold,
            "utility_loss": selected.utility_loss,
            "reid_at_1": selected.reid_at_1,
            "link_auc": selected.link_auc,
        },
        "estimator": {
            "type": "ridge",
            "ridge": estimator.ridge,
            "training_rows": len(estimator_rows),
            "method_filter": estimator_method,
            "source": str(args.attack_artifact),
        },
        # ``rows`` is deliberately restricted to the selected method because
        # the proxy loads this field for its online estimator. Keep the full
        # attack table separately for reporting and auditability.
        "rows": estimator_rows,
        "attack_rows": attack_rows,
        "protocol": "development-only threshold selection; test split is untouched",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}; T={threshold:.6f}; rows={len(attack_rows)}")


if __name__ == "__main__":
    main()
