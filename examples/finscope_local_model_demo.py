"""Run FinScope with a local small Transformers model.

Example (requires a separate environment with torch and transformers):

    python3 examples/finscope_local_model_demo.py \
        --model /path/to/Qwen3-0.6B --device cuda:0
"""

from __future__ import annotations

import argparse

from finscope import FinScopeMediator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="local instruct model path")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    mediator = FinScopeMediator.from_local_model(
        args.model,
        [
            {"name": "苹果公司", "aliases": ["AAPL"]},
            {"name": "贵州茅台", "aliases": ["600519"]},
        ],
        device=args.device,
    )
    scope = mediator.open_scope("local-model-demo", "2026-08-15")
    raw = "请分析 AAPL 和贵州茅台，随后生成目标权重。"
    anonymized = mediator.sanitize_prompt(raw, scope)
    print("Original:", raw)
    print("External sees:", anonymized)
    print("Local restore:", mediator.restore_output(anonymized, scope))
    print("Metrics:", mediator.get_metrics(scope))


if __name__ == "__main__":
    main()
