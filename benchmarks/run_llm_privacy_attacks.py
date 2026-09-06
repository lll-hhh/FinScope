"""Run the training-free LLM privacy attacker on supported benchmarks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Iterable

from benchmarks.llm_attack_adapters import (
    PRIOR_LEVELS,
    finvault_batches,
    nlpcc_batches,
    stockbench_batches,
)
from benchmarks.llm_privacy_attacker import AttackBatch, LlmPrivacyAttacker, public_batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("stockbench", "nlpcc", "finvault"), required=True)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--benchmark-root", type=Path)
    parser.add_argument("--nlpcc-result", type=Path)
    parser.add_argument("--methods", nargs="+", default=["fixed_alias", "episode_alias", "finscope"])
    parser.add_argument("--prior-levels", nargs="+", choices=PRIOR_LEVELS, default=list(PRIOR_LEVELS))
    parser.add_argument("--trace-lengths", nargs="+", type=int, default=[1, 5, 20, 0])
    parser.add_argument("--attacker-base-url", default="http://127.0.0.1:18002/v1")
    parser.add_argument("--attacker-model", default="qwen35_4b")
    parser.add_argument("--max-tokens", type=int, default=3072)
    parser.add_argument("--max-identity-targets", type=int, default=40)
    parser.add_argument("--max-link-pairs", type=int, default=80)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt-audit", type=Path)
    return parser.parse_args()


def batches(args: argparse.Namespace) -> Iterable[AttackBatch]:
    common = {
        "methods": args.methods,
        "prior_levels": args.prior_levels,
        "trace_lengths": args.trace_lengths,
        "max_identity_targets": args.max_identity_targets,
        "max_link_pairs": args.max_link_pairs,
        "seed": args.seed,
    }
    if args.benchmark == "stockbench":
        if args.audit_dir is None or args.benchmark_root is None:
            raise ValueError("StockBench requires --audit-dir and --benchmark-root")
        return stockbench_batches(
            audit_dir=args.audit_dir,
            stockbench_root=args.benchmark_root,
            **common,
        )
    if args.benchmark == "nlpcc":
        if args.nlpcc_result is None or args.benchmark_root is None:
            raise ValueError("NLPCC requires --nlpcc-result and --benchmark-root")
        return nlpcc_batches(
            result_path=args.nlpcc_result,
            nlpcc_root=args.benchmark_root,
            **common,
        )
    if args.audit_dir is None or args.benchmark_root is None:
        raise ValueError("FinVault requires --audit-dir and --benchmark-root")
    return finvault_batches(
        audit_dir=args.audit_dir,
        finvault_root=args.benchmark_root,
        max_candidates=args.max_candidates,
        **common,
    )


def key(value: Dict[str, Any] | AttackBatch) -> str:
    if isinstance(value, AttackBatch):
        parts = (value.benchmark, value.method, value.prior_level, value.trace_length)
    else:
        parts = (
            str(value.get("benchmark")),
            str(value.get("method")),
            str(value.get("prior_level")),
            str(value.get("trace_length")),
        )
    return "|".join(parts)


def load_output(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "metadata": {}, "rows": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError(f"invalid checkpoint: {path}")
    return value


def write_output(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    attacker = LlmPrivacyAttacker(
        base_url=args.attacker_base_url,
        model=args.attacker_model,
        max_tokens=args.max_tokens,
    )
    output = load_output(args.output)
    completed = {key(row) for row in output["rows"] if row.get("status") == "ok"}
    output["metadata"].update(
        {
            "protocol": "training-free LLM identity ranking and trajectory linkage",
            "benchmark": args.benchmark,
            "attacker_model": args.attacker_model,
            "temperature": 0.0,
            "ground_truth_in_prompt": False,
            "candidate_ids_in_prompt": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    prompt_handle = None
    if args.prompt_audit:
        args.prompt_audit.parent.mkdir(parents=True, exist_ok=True)
        prompt_handle = args.prompt_audit.open("a", encoding="utf-8")
    try:
        for batch in batches(args):
            batch_key = key(batch)
            if batch_key in completed:
                continue
            if prompt_handle is not None:
                prompt_handle.write(json.dumps(public_batch(batch), ensure_ascii=False) + "\n")
                prompt_handle.flush()
            print(f"attacking {batch_key}", flush=True)
            try:
                row = attacker.attack(batch, include_raw=args.include_raw)
                row["status"] = "ok"
            except Exception as exc:
                row = {
                    "benchmark": batch.benchmark,
                    "method": batch.method,
                    "prior_level": batch.prior_level,
                    "trace_length": batch.trace_length,
                    "status": "error",
                    "error": str(exc)[:500],
                }
            output["rows"] = [item for item in output["rows"] if key(item) != batch_key]
            output["rows"].append(row)
            output["metadata"]["attacker_usage"] = attacker.metadata()["usage"]
            write_output(args.output, output)
    finally:
        if prompt_handle is not None:
            prompt_handle.close()
    errors = sum(row.get("status") != "ok" for row in output["rows"])
    print(f"wrote {args.output}: {len(output['rows'])} rows, {errors} errors", flush=True)


if __name__ == "__main__":
    main()
