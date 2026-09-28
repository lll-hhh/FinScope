"""Build the empirical online risk lookup from zero-shot LLM attacks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack", type=Path, required=True)
    parser.add_argument("--method", default="finscope")
    parser.add_argument(
        "--prior-level",
        default="K4",
        help="public-prior level used for the conservative lookup (default: K4)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.attack.read_text(encoding="utf-8"))
    source_rows = source.get("rows", []) if isinstance(source, Mapping) else []
    rows = []
    for source_row in source_rows:
        if not isinstance(source_row, Mapping):
            continue
        if (
            source_row.get("status") != "ok"
            or source_row.get("method") != args.method
            or source_row.get("prior_level") != args.prior_level
        ):
            continue
        if not isinstance(source_row.get("exposure_state"), Mapping):
            continue
        row: Dict[str, Any] = dict(source_row)
        # A one-step trace has no cross-step pairs.  It represents the random
        # linkage baseline for lookup, while the reported table keeps Link
        # AUC undefined for that individual experiment cell.
        if row.get("link_auc") is None:
            row["link_auc"] = 0.5
            row["link_auc_imputed_for_lookup"] = True
        rows.append(row)
    if not rows:
        raise ValueError("no successful attack rows with exposure_state were found")

    result = {
        "schema_version": 2,
        "type": "empirical_lookup",
        "protocol": "Qwen3.5-4B zero-shot K4 attack outcomes indexed by local exposure state; no trained risk model",
        "method_filter": args.method,
        "prior_level_filter": args.prior_level,
        "source": str(args.attack),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lookup_rule": {
            "exposure_index": "equal mean of the seven capped local exposure features",
            "interpolation": "piecewise linear",
            "monotonicity": "cumulative upper envelope of measured ReID and linkage risk",
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}: {len(rows)} rows")


if __name__ == "__main__":
    main()
