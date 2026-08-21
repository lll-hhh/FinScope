"""Run a small privacy/utility/cost benchmark for FinScope.

The decision cases use the public NLPCC 2026 ETF candidate universe, but the
decision scores are synthetic and deterministic. Results from this runner are
therefore middleware smoke results, not financial backtest returns.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import statistics
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib import request

from finscope import ActionValidationError, FinScopeMediator


NLPCC_ASSETS: Tuple[str, ...] = (
    "000300.SH",
    "000905.SH",
    "399006.SZ",
    "000688.SH",
    "518880.SH",
    "512880.SH",
    "512800.SH",
    "512070.SH",
    "159995.SZ",
    "159819.SZ",
    "515880.SH",
    "512010.SH",
)

METHODS = ("vanilla", "deletion", "global_alias", "finscope")


@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    task_id: str
    trading_day: str
    candidates: Tuple[str, ...]
    decision_scores: Tuple[float, ...]
    expected_asset: str
    expected_side: str = "buy"
    expected_weight: float = 0.55

    def payload(self) -> Dict[str, Any]:
        return {
            "agent_role": "trader",
            "candidate_pool": list(self.candidates),
            "signals": [
                {"asset": asset, "decision_score": score}
                for asset, score in zip(self.candidates, self.decision_scores)
            ],
            "constraints": {
                "allowed_sides": ["buy"],
                "target_weight": self.expected_weight,
                "max_weight": 0.60,
            },
        }


@dataclass(frozen=True)
class BackendResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


@dataclass
class CaseResult:
    method: str
    case_id: str
    task_id: str
    trading_day: str
    parsed: bool
    valid: bool
    decision_correct: bool
    weight_error: float
    direct_identifier_leak: bool
    input_tokens: int
    output_tokens: int
    model_latency_ms: float
    preprocess_ms: float
    postprocess_ms: float
    total_latency_ms: float
    raw_output: str
    restored_action: Optional[Dict[str, Any]]


class DeterministicBackend:
    """Reference executor that isolates middleware behavior from model quality."""

    name = "deterministic-reference"
    metadata = {"kind": "deterministic-reference"}

    def generate(self, prompt: str) -> BackendResult:
        started = time.perf_counter()
        payload = _extract_input_payload(prompt)
        signals = payload.get("signals", [])
        if not isinstance(signals, list) or not signals:
            output = {"error": "missing signals"}
        else:
            best = max(signals, key=lambda item: float(item["decision_score"]))
            constraints = payload.get("constraints", {})
            output = {
                "asset": best.get("asset"),
                "side": "buy",
                "weight": constraints.get("target_weight", 0.55),
            }
        text = json.dumps(output, ensure_ascii=False)
        latency_ms = (time.perf_counter() - started) * 1000
        return BackendResult(
            text=text,
            input_tokens=_token_estimate(prompt),
            output_tokens=_token_estimate(text),
            latency_ms=latency_ms,
        )


class OpenAIBackend:
    """Minimal OpenAI-compatible backend for vLLM/SGLang endpoints."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: Optional[str] = None,
        max_new_tokens: int = 96,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_new_tokens = max_new_tokens
        self.name = f"openai:{model}"
        self.metadata = {
            "kind": "openai-compatible",
            "base_url": self.base_url,
            "model": model,
        }

    def generate(self, prompt: str) -> BackendResult:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": self.max_new_tokens,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        with request.urlopen(req, timeout=180) as response:
            document = json.loads(response.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - started) * 1000
        text = document["choices"][0]["message"]["content"]
        usage = document.get("usage", {})
        return BackendResult(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", _token_estimate(prompt))),
            output_tokens=int(usage.get("completion_tokens", _token_estimate(text))),
            latency_ms=latency_ms,
        )


class TransformersBackend:
    """Direct local Qwen3.8 backend; imports heavy dependencies lazily."""

    def __init__(self, model_path: str, device: str, max_new_tokens: int = 96) -> None:
        import torch
        import transformers
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self._torch = torch
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.processor = AutoProcessor.from_pretrained(
            model_path, local_files_only=True
        )
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map=device,
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()
        self.name = f"transformers:{model_path}"
        self.metadata = {
            "kind": "transformers",
            "model_path": model_path,
            "model_type": self.model.config.model_type,
            "architectures": self.model.config.architectures,
            "transformers_version": transformers.__version__,
            "device": device,
            "dtype": str(self.model.dtype),
        }

    def generate(self, prompt: str) -> BackendResult:
        messages = [{"role": "user", "content": prompt}]
        formatted = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = self.processor(text=formatted, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        input_tokens = int(inputs["input_ids"].shape[-1])
        started = time.perf_counter()
        with self._torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        output_ids = generated[0][input_tokens:]
        text = self.processor.tokenizer.decode(
            output_ids, skip_special_tokens=True
        )
        return BackendResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=int(output_ids.shape[-1]),
            latency_ms=latency_ms,
        )


def build_cases(task_count: int = 6) -> List[DecisionCase]:
    cases: List[DecisionCase] = []
    for task_index in range(task_count):
        start = (task_index * 2) % len(NLPCC_ASSETS)
        candidates = tuple(
            NLPCC_ASSETS[(start + offset) % len(NLPCC_ASSETS)]
            for offset in range(3)
        )
        for day_offset, trading_day in enumerate(("2026-06-01", "2026-06-02")):
            winner = (task_index + day_offset) % len(candidates)
            scores = [0.21, 0.43, 0.67]
            scores[winner] = 0.91
            cases.append(
                DecisionCase(
                    case_id=f"task-{task_index:02d}-day-{day_offset + 1}",
                    task_id=f"task-{task_index:02d}",
                    trading_day=trading_day,
                    candidates=candidates,
                    decision_scores=tuple(scores),
                    expected_asset=candidates[winner],
                )
            )
    return cases


def build_prompt(payload: Mapping[str, Any]) -> str:
    return (
        "You are a financial allocation agent. Select the candidate with the "
        "highest decision_score. Return JSON only with keys asset, side, and "
        "weight. Copy asset exactly from the input, use side=buy, and use the "
        "constraints.target_weight value.\nBEGIN_INPUT_JSON\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\nEND_INPUT_JSON"
    )


def run_benchmark(
    backend: Any,
    *,
    task_count: int = 6,
    methods: Sequence[str] = METHODS,
) -> Dict[str, Any]:
    unknown = set(methods) - set(METHODS)
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")
    cases = build_cases(task_count)
    catalog = [{"name": asset} for asset in NLPCC_ASSETS]
    global_aliases = {
        asset: f"GLOBAL_ASSET_{index:03d}"
        for index, asset in enumerate(NLPCC_ASSETS, start=1)
    }
    global_restore = {alias: asset for asset, alias in global_aliases.items()}
    all_results: List[CaseResult] = []
    representations: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {
        method: {} for method in methods
    }

    for method in methods:
        mediator = FinScopeMediator(catalog) if method == "finscope" else None
        for case in cases:
            payload = case.payload()
            scope = None
            preprocess_started = time.perf_counter()
            if method == "vanilla":
                outbound = payload
            elif method == "deletion":
                outbound = _replace_entities(
                    payload,
                    {asset: "[REDACTED]" for asset in NLPCC_ASSETS},
                )
            elif method == "global_alias":
                outbound = _replace_entities(payload, global_aliases)
            else:
                assert mediator is not None
                scope = mediator.open_scope(
                    case.task_id,
                    case.trading_day,
                    conversation_id="benchmark",
                )
                outbound = mediator.sanitize_tool_result(payload, scope)

            outbound_candidates = outbound.get("candidate_pool", [])
            representations[method].setdefault(case.task_id, {})[
                case.trading_day
            ] = {
                original: transformed
                for original, transformed in zip(case.candidates, outbound_candidates)
                if isinstance(transformed, str)
            }
            outbound_text = json.dumps(outbound, ensure_ascii=False)
            direct_leak = any(asset in outbound_text for asset in NLPCC_ASSETS)
            prompt = build_prompt(outbound)
            preprocess_ms = (time.perf_counter() - preprocess_started) * 1000
            backend_result = backend.generate(prompt)
            postprocess_started = time.perf_counter()
            parsed_action = _extract_json_object(backend_result.text)
            restored: Optional[Dict[str, Any]] = None
            valid = False
            if parsed_action is not None:
                try:
                    if method == "global_alias":
                        restored = _replace_entities(parsed_action, global_restore)
                        valid = _plain_action_valid(restored, case.candidates)
                    elif method == "finscope":
                        assert mediator is not None and scope is not None
                        restored = mediator.validate_action(parsed_action, scope).action
                        valid = True
                    else:
                        restored = dict(parsed_action)
                        valid = _plain_action_valid(restored, case.candidates)
                except (ActionValidationError, KeyError, TypeError, ValueError):
                    valid = False
            decision_correct = bool(
                valid
                and restored is not None
                and restored.get("asset") == case.expected_asset
                and str(restored.get("side", "")).casefold() == case.expected_side
            )
            if valid and restored is not None and isinstance(
                restored.get("weight"), (int, float)
            ):
                weight_error = abs(float(restored["weight"]) - case.expected_weight)
            else:
                weight_error = 1.0
            postprocess_ms = (time.perf_counter() - postprocess_started) * 1000
            total_latency_ms = (
                preprocess_ms + backend_result.latency_ms + postprocess_ms
            )
            all_results.append(
                CaseResult(
                    method=method,
                    case_id=case.case_id,
                    task_id=case.task_id,
                    trading_day=case.trading_day,
                    parsed=parsed_action is not None,
                    valid=valid,
                    decision_correct=decision_correct,
                    weight_error=weight_error,
                    direct_identifier_leak=direct_leak,
                    input_tokens=backend_result.input_tokens,
                    output_tokens=backend_result.output_tokens,
                    model_latency_ms=backend_result.latency_ms,
                    preprocess_ms=preprocess_ms,
                    postprocess_ms=postprocess_ms,
                    total_latency_ms=total_latency_ms,
                    raw_output=backend_result.text,
                    restored_action=restored,
                )
            )

    metrics = {
        method: _aggregate_method(
            [result for result in all_results if result.method == method],
            representations[method],
        )
        for method in methods
    }
    return {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "backend": backend.name,
            "backend_metadata": getattr(backend, "metadata", {}),
            "benchmark": "FinDecisionBench-S",
            "benchmark_scope": (
                "NLPCC 2026 ETF universe with synthetic deterministic scores; "
                "not a historical return backtest"
            ),
            "tasks": task_count,
            "cases": len(cases),
            "methods": list(methods),
        },
        "metrics": metrics,
        "robustness": run_robustness_checks(),
        "cases": [asdict(result) for result in all_results],
    }


def run_robustness_checks() -> Dict[str, Any]:
    catalog = [{"name": "000300.SH"}, {"name": "000905.SH"}]
    mediator = FinScopeMediator(catalog)
    day_one = mediator.open_scope("robust-task", "2026-06-01", conversation_id="shared")
    mediator.set_candidate_pool(day_one, ["000300.SH"])
    alias_research = mediator.get_alias("000300.SH", day_one)
    alias_trade = mediator.get_alias("000300.SH", day_one)
    checks = {
        "cross_agent_alias_consistency": alias_research == alias_trade,
        "direct_identifier_removed": "000300.SH"
        not in mediator.sanitize_prompt("研究 000300.SH", day_one),
        "known_alias_restored": mediator.restore_output(alias_research, day_one)
        == "000300.SH",
    }
    try:
        mediator.validate_action(
            {"asset": "000905.SH", "side": "buy", "quantity": 1}, day_one
        )
        checks["out_of_pool_rejected"] = False
    except ActionValidationError:
        checks["out_of_pool_rejected"] = True
    try:
        mediator.validate_action(
            {"asset": "000300.SH", "side": "borrow", "quantity": 1}, day_one
        )
        checks["invalid_side_rejected"] = False
    except ActionValidationError:
        checks["invalid_side_rejected"] = True
    try:
        mediator.validate_action(
            {"asset": "FS_ASSET_AAAAAAAA", "side": "buy", "quantity": 1},
            day_one,
        )
        checks["unknown_alias_rejected"] = False
    except ActionValidationError:
        checks["unknown_alias_rejected"] = True
    day_two = mediator.open_scope(
        "robust-task", "2026-06-02", conversation_id="shared"
    )
    alias_day_two = mediator.get_alias("000300.SH", day_two)
    checks["cross_day_alias_rotation"] = alias_research != alias_day_two
    checks["weight_bound_rejected"] = False
    mediator.set_candidate_pool(day_two, ["000300.SH"])
    try:
        mediator.validate_action(
            {"asset": "000300.SH", "side": "buy", "weight": 1.5}, day_two
        )
    except ActionValidationError:
        checks["weight_bound_rejected"] = True
    passed = sum(checks.values())
    return {"passed": passed, "total": len(checks), "checks": checks}


def render_markdown(report: Mapping[str, Any]) -> str:
    metadata = report["metadata"]
    lines = [
        "# FinScope Main Table",
        "",
        f"Backend: `{metadata['backend']}`  ",
        f"Benchmark: `{metadata['benchmark']}` ({metadata['cases']} cases)  ",
        f"Scope: {metadata['benchmark_scope']}",
        "",
        "| Method | Decision Acc. ↑ | Valid Action ↑ | Weight MAE ↓ | Direct Leak ↓ | Cross-day Link ↓ | Avg Input Tokens ↓ | Local p95 (ms) ↓ | E2E p95 (ms) ↓ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method in metadata["methods"]:
        metric = report["metrics"][method]
        lines.append(
            "| {method} | {decision:.1%} | {valid:.1%} | {mae:.4f} | "
            "{leak:.1%} | {link:.1%} | {tokens:.1f} | {local:.3f} | "
            "{total:.2f} |".format(
                method=method,
                decision=metric["decision_accuracy"],
                valid=metric["valid_action_rate"],
                mae=metric["weight_mae"],
                leak=metric["direct_identifier_leak_rate"],
                link=metric["cross_day_unique_link_rate"],
                tokens=metric["avg_input_tokens"],
                local=metric["p95_local_overhead_ms"],
                total=metric["p95_total_latency_ms"],
            )
        )
    robustness = report["robustness"]
    lines.extend(
        [
            "",
            f"Middleware robustness checks: **{robustness['passed']}/{robustness['total']} passed**.",
            "",
            "`deterministic-reference` uses a tokenizer-independent token estimate. "
            "Model-backed runs use the backend's reported tokenizer counts.",
        ]
    )
    return "\n".join(lines) + "\n"


def _aggregate_method(
    results: Sequence[CaseResult],
    representations: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> Dict[str, Any]:
    count = len(results)
    if count == 0:
        raise ValueError("cannot aggregate an empty method result")
    return {
        "cases": count,
        "parse_rate": sum(result.parsed for result in results) / count,
        "valid_action_rate": sum(result.valid for result in results) / count,
        "decision_accuracy": sum(result.decision_correct for result in results) / count,
        "weight_mae": statistics.fmean(result.weight_error for result in results),
        "direct_identifier_leak_rate": sum(
            result.direct_identifier_leak for result in results
        )
        / count,
        "cross_day_unique_link_rate": _cross_day_unique_link_rate(representations),
        "avg_input_tokens": statistics.fmean(
            result.input_tokens for result in results
        ),
        "avg_output_tokens": statistics.fmean(
            result.output_tokens for result in results
        ),
        "avg_model_latency_ms": statistics.fmean(
            result.model_latency_ms for result in results
        ),
        "p95_model_latency_ms": _percentile(
            [result.model_latency_ms for result in results], 0.95
        ),
        "avg_local_overhead_ms": statistics.fmean(
            result.preprocess_ms + result.postprocess_ms for result in results
        ),
        "p95_local_overhead_ms": _percentile(
            [result.preprocess_ms + result.postprocess_ms for result in results],
            0.95,
        ),
        "avg_total_latency_ms": statistics.fmean(
            result.total_latency_ms for result in results
        ),
        "p95_total_latency_ms": _percentile(
            [result.total_latency_ms for result in results], 0.95
        ),
    }


def _cross_day_unique_link_rate(
    representations: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> float:
    linked = 0
    comparable = 0
    for day_map in representations.values():
        if len(day_map) < 2:
            continue
        days = sorted(day_map)
        first = day_map[days[0]]
        second = day_map[days[1]]
        first_unique = len(set(first.values())) == len(first)
        second_unique = len(set(second.values())) == len(second)
        for asset in set(first) & set(second):
            comparable += 1
            if first_unique and second_unique and first[asset] == second[asset]:
                linked += 1
    return linked / comparable if comparable else 0.0


def _plain_action_valid(action: Mapping[str, Any], candidates: Sequence[str]) -> bool:
    asset = action.get("asset")
    side = action.get("side")
    weight = action.get("weight")
    return bool(
        isinstance(asset, str)
        and asset in candidates
        and isinstance(side, str)
        and side.casefold() == "buy"
        and isinstance(weight, (int, float))
        and not isinstance(weight, bool)
        and math.isfinite(float(weight))
        and 0 <= float(weight) <= 1
    )


def _replace_entities(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for source in sorted(replacements, key=len, reverse=True):
            result = result.replace(source, replacements[source])
        return result
    if isinstance(value, Mapping):
        return {
            _replace_entities(key, replacements) if isinstance(key, str) else key:
            _replace_entities(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_replace_entities(item, replacements) for item in value]
    return value


def _extract_input_payload(prompt: str) -> Dict[str, Any]:
    match = re.search(
        r"BEGIN_INPUT_JSON\s*(\{.*\})\s*END_INPUT_JSON",
        prompt,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError("benchmark prompt does not contain input JSON")
    document = json.loads(match.group(1))
    if not isinstance(document, dict):
        raise ValueError("input JSON must be an object")
    return document


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            document, _ = decoder.raw_decode(raw[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict):
            return document
    return None


def _token_estimate(text: str) -> int:
    ascii_tokens = re.findall(r"[A-Za-z0-9_.-]+|[^\x00-\x7F]", text)
    return max(1, len(ascii_tokens))


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _build_backend(args: argparse.Namespace) -> Any:
    if args.backend == "deterministic":
        return DeterministicBackend()
    if args.backend == "openai":
        api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
        return OpenAIBackend(
            args.base_url,
            args.model,
            api_key=api_key,
            max_new_tokens=args.max_new_tokens,
        )
    return TransformersBackend(
        args.model,
        args.device,
        max_new_tokens=args.max_new_tokens,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=("deterministic", "openai", "transformers"),
        default="deterministic",
    )
    parser.add_argument("--model", default="../models/Qwen3.8-27B")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--tasks", type=int, default=6)
    parser.add_argument("--methods", default=",".join(METHODS))
    parser.add_argument("--output-dir", default="benchmarks/results")
    args = parser.parse_args()

    methods = tuple(item.strip() for item in args.methods.split(",") if item.strip())
    backend = _build_backend(args)
    report = run_benchmark(backend, task_count=args.tasks, methods=methods)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.backend.replace("/", "-")
    json_path = output_dir / f"main_table_{suffix}.json"
    markdown_path = output_dir / f"main_table_{suffix}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
