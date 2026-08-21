"""Split selected methods from a completed multi-method NLPCC result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--methods", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.input)
    document = json.loads(source.read_text(encoding="utf-8"))
    available = {row["method"] for row in document["main_table"]}
    missing = set(args.methods) - available
    if missing:
        raise ValueError(f"source result lacks methods: {sorted(missing)}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for method in args.methods:
        shard = {
            "metadata": {
                **document["metadata"],
                "methods": [method],
                "source_result_files": [str(source)],
            },
            "main_table": [
                row for row in document["main_table"] if row["method"] == method
            ],
            "daily_records": [
                row for row in document["daily_records"] if row["method"] == method
            ],
            "portfolio_value_history": {
                method: document["portfolio_value_history"][method]
            },
        }
        output = output_dir / f"{source.stem}_{method}.json"
        output.write_text(
            json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {output}")


if __name__ == "__main__":
    main()
