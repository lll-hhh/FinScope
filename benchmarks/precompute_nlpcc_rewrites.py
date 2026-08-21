"""Precompute independent daily LLM Rewrite calls for the NLPCC backtest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from benchmarks.run_benchmark import TransformersBackend
from benchmarks.run_nlpcc_real import (
    MODEL_REVISION,
    Portfolio,
    build_payload,
    load_official_data,
    news_titles_sha256,
    rewrite_news,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nlpcc-root", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--start-date", default="2025-01-02")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--lookback-days", type=int, default=6)
    parser.add_argument("--top-rank", type=int, default=20)
    parser.add_argument("--pre-k-days", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def write_output(path: Path, metadata: Dict[str, Any], entries: Dict[str, Any]) -> None:
    payload = {"metadata": metadata, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    if args.shard_count <= 0 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("shard index must be in [0, shard count)")
    loader, dates, _ = load_official_data(args)
    selected = dates[args.shard_index :: args.shard_count]
    output = Path(args.output)
    metadata = {
        "benchmark": "NLPCC 2026 Track 1 public A-set",
        "model": args.model,
        "model_revision": MODEL_REVISION,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "dates": selected,
    }
    entries: Dict[str, Any] = {}
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if previous.get("metadata") != metadata:
            raise RuntimeError("existing rewrite cache has incompatible metadata")
        entries.update(previous.get("entries", {}))
    backend = TransformersBackend(args.model, args.device, args.max_new_tokens)
    for index, date in enumerate(selected, start=1):
        key = str(date)
        if key in entries:
            continue
        payload = build_payload(loader, date, Portfolio(), args)
        source_hash = news_titles_sha256(payload)
        rewritten, usage, succeeded = rewrite_news(backend, payload)
        entries[key] = {
            "source_titles_sha256": source_hash,
            "safe_titles": [str(item.get("title", "")) for item in rewritten["news"]],
            "succeeded": succeeded,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "latency_ms": usage.latency_ms,
            },
        }
        write_output(output, metadata, entries)
        print(f"[{index}/{len(selected)}] {date} succeeded={succeeded}", flush=True)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
