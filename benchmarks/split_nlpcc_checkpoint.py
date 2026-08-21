"""Split a multi-method NLPCC checkpoint into resumable method shards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.run_nlpcc_real import load_official_data, run_fingerprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--methods", nargs="+", required=True)
    parser.add_argument("--nlpcc-root", default="../data/nlpcc2026_20260818")
    parser.add_argument("--model", default="../models/Qwen3.8-27B")
    parser.add_argument("--start-date", default="2025-01-02")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--lookback-days", type=int, default=6)
    parser.add_argument("--top-rank", type=int, default=20)
    parser.add_argument("--pre-k-days", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--disclosure-level", default="P3")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    completed = int(source["completed_days"])
    missing = set(args.methods) - set(source["portfolios"])
    if missing:
        raise ValueError("source checkpoint lacks methods: %s" % sorted(missing))
    records = [row for row in source["records"] if row["method"] in args.methods]
    expected = completed * len(args.methods)
    if len(records) != expected:
        raise ValueError("expected %d records, found %d" % (expected, len(records)))

    loader_args = SimpleNamespace(**vars(args))
    _, dates, _ = load_official_data(loader_args)
    target_args = SimpleNamespace(**vars(args))
    target_args.methods = list(args.methods)
    payload = {
        "fingerprint": run_fingerprint(target_args, dates),
        "completed_days": completed,
        "portfolios": {method: source["portfolios"][method] for method in args.methods},
        "values": {method: source["values"][method] for method in args.methods},
        "representations": {
            method: source["representations"][method] for method in args.methods
        },
        "records": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print("wrote %s at %d completed days" % (output, completed))


if __name__ == "__main__":
    main()
