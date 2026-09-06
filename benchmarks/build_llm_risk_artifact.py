"""Build the online risk-estimator artifact from LLM attack results."""

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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.attack.read_text(encoding="utf-8"))
    source_rows = source.get("rows", []) if isinstance(source, Mapping) else []
    rows = []
    for source_row in source_rows:
        if not isinstance(source_row, Mapping):
            continue
        if source_row.get("status") != "ok" or source_row.get("method") != args.method:
            continue
        if not isinstance(source_row.get("exposure_state"), Mapping):
            continue
        row: Dict[str, Any] = dict(source_row)
        # A one-step trace has no cross-step pairs.  It represents the random
        # linkage baseline for fitting, while the reported table keeps Link
        # AUC undefined for that individual experiment cell.
        if row.get("link_auc") is None:
            row["link_auc"] = 0.5
            row["link_auc_imputed_for_estimator"] = True
        rows.append(row)
    if not rows:
        raise ValueError("no successful attack rows with exposure_state were found")

    result = {
        "schema_version": 1,
        "protocol": "Qwen3.5-4B attack outcomes mapped from local exposure state",
        "method_filter": args.method,
        "source": str(args.attack),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}: {len(rows)} rows")


if __name__ == "__main__":
    main()
