"""Build FinScope's empirical risk lookup and select T on development data.

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

from finscope import (
    DevPolicyResult,
    build_empirical_risk_lookup,
    calibrate_threshold,
)


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
        "--lookup-method",
        default="finscope",
        help="method whose K4 attack rows populate the online lookup (default: finscope)",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    attack_rows = list(_rows(args.attack_artifact))
    utility_rows = list(_rows(args.utility_artifact))
    if not attack_rows:
        raise ValueError("attack artifact has no rows")
    lookup_method = str(args.lookup_method).strip()
    lookup_rows = (
        [row for row in attack_rows if str(row.get("method", "")) == lookup_method]
        if lookup_method
        else attack_rows
    )
    if not lookup_rows:
        raise ValueError(
            "attack artifact has no rows for lookup method %r" % lookup_method
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
                bool(row.get("eligible", row.get("non_degenerate", True))),
            )
        )
    threshold = calibrate_threshold(candidates, max_utility_loss=args.max_utility_loss)
    lookup = build_empirical_risk_lookup(lookup_rows)
    selected = min(
        (
            item for item in candidates
            if item.eligible and item.utility_loss <= args.max_utility_loss
        ),
        key=lambda item: (item.privacy_risk, item.threshold),
    )
    result: Dict[str, Any] = {
        "schema_version": 2,
        "threshold": threshold,
        "max_utility_loss": args.max_utility_loss,
        "selected_development_policy": {
            "threshold": selected.threshold,
            "utility_loss": selected.utility_loss,
            "reid_at_1": selected.reid_at_1,
            "link_auc": selected.link_auc,
        },
        "risk_lookup": {
            "type": "empirical_lookup",
            "observation_rows": lookup.observation_count,
            "points": [
                {
                    "exposure_index": index,
                    "reid_at_1": risk.reid_at_1,
                    "link_auc": risk.link_auc,
                }
                for index, risk in lookup.points
            ],
            "method_filter": lookup_method,
            "source": str(args.attack_artifact),
            "training": False,
        },
        # ``rows`` is deliberately restricted to the selected method because
        # the proxy loads this field for its online lookup. Keep the full
        # attack table separately for reporting and auditability.
        "rows": lookup_rows,
        "attack_rows": attack_rows,
        "protocol": "development-only threshold selection; test split is untouched",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}; T={threshold:.6f}; rows={len(attack_rows)}")


if __name__ == "__main__":
    main()
