"""Run the fixed NLPCC development-window ablation for local privacy models.

The task model, data window, disclosure level and JSON protocol stay fixed. Only
the local recognizer/planner/auditor model changes. Missing weights are reported
as missing rather than silently replaced by a fallback model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
from typing import Any, Dict, Mapping, Sequence
from urllib.error import URLError
from urllib.request import urlopen


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int(fraction * len(ordered) + 0.999999) - 1))
    return ordered[index]


def load_manifest(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models")
    if not isinstance(models, list) or len(models) != 10:
        raise ValueError("local privacy model manifest must contain exactly 10 models")
    ids = [item.get("model_id") for item in models]
    if len(set(ids)) != len(ids):
        raise ValueError("local privacy model IDs must be unique")
    maximum = float(payload.get("max_parameters_b", 4.0))
    if any(float(item["parameters_b"]) > maximum for item in models):
        raise ValueError("manifest contains a model above the configured size limit")
    if any(not item.get("instruction_tuned") for item in models):
        raise ValueError("all local privacy models must be instruction tuned")
    return payload


def wait_health(url: str, process: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    health_url = url.rstrip("/") + "/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"privacy model server exited with code {process.returncode}")
        try:
            with urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(1)
    raise TimeoutError(f"privacy model server did not become healthy: {health_url}")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=20)


def summarize_result(document: Mapping[str, Any]) -> Dict[str, Any]:
    rows = [
        row for row in document.get("daily_records", [])
        if row.get("method") == "finscope"
    ]
    main = next(
        (row for row in document.get("main_table", []) if row.get("method") == "finscope"),
        {},
    )
    # ``LocalPrivacyAgent.get_metrics`` uses role-qualified names. Keep the
    # compact names in the selection report, but map them explicitly here;
    # silently reading missing keys would make every model look unmeasured
    # and could select a failed model by latency alone.
    metric_keys = {
        "planner_calls": "disclosure_planner_calls",
        "planner_successes": "disclosure_planner_successes",
        "planner_repairs": "disclosure_planner_repairs",
        "planner_fallbacks": "disclosure_planner_fallbacks",
        "recognizer_calls": "entity_recognizer_model_calls",
        "recognizer_failures": "entity_recognizer_model_failures",
        "recognizer_fallbacks": "entity_recognizer_fallbacks",
        "auditor_calls": "recovery_auditor_calls",
        "auditor_failures": "recovery_auditor_failures",
    }
    counters = {key: 0 for key in metric_keys}
    local_tokens = 0.0
    local_latencies = []
    for row in rows:
        metrics = row.get("privacy_agent_metrics") or {}
        for key, metric_key in metric_keys.items():
            counters[key] += int(metrics.get(metric_key, 0))
        usage = row.get("privacy_model_usage") or {}
        local_tokens += float(usage.get("prompt_tokens", 0))
        local_tokens += float(usage.get("completion_tokens", 0))
        local_latencies.append(
            float(row.get("preprocess_ms", 0.0))
            + float(row.get("postprocess_ms", 0.0))
        )
    planner_calls = counters["planner_calls"]
    recognizer_calls = counters["recognizer_calls"]
    auditor_calls = counters["auditor_calls"]
    return {
        "trading_days": len({row.get("date") for row in rows}),
        "assets_or_actions": len(rows),
        "strict_planner_valid": (
            counters["planner_successes"] / planner_calls if planner_calls else None
        ),
        "planner_repair_rate": (
            counters["planner_repairs"] / planner_calls if planner_calls else None
        ),
        "recognizer_failure_rate": (
            counters["recognizer_failures"] / recognizer_calls if recognizer_calls else None
        ),
        "auditor_failure_rate": (
            counters["auditor_failures"] / auditor_calls if auditor_calls else None
        ),
        "fallback_count": counters["planner_fallbacks"] + counters["recognizer_fallbacks"],
        "privacy_agent_tokens": local_tokens,
        "privacy_agent_p95_ms": percentile(local_latencies, 0.95),
        "nlpcc_valid": main.get("valid_action_rate"),
        "sharpe": main.get("sharpe"),
        "return": main.get("total_return"),
        "mdd": main.get("max_drawdown"),
        **counters,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="benchmarks/local_privacy_models.json")
    parser.add_argument("--model-root", default="/home/zgx/models")
    parser.add_argument("--nlpcc-root", required=True)
    parser.add_argument("--task-model", default="/home/zgx/models/Qwen3.8-27B")
    parser.add_argument("--task-model-base-url", required=True)
    parser.add_argument("--development-days", type=int, default=20)
    parser.add_argument("--device", default="cuda:4")
    parser.add_argument("--privacy-port", type=int, default=8120)
    parser.add_argument("--output-root", default="benchmarks/results/local_model_ablation")
    parser.add_argument("--run-timeout", type=float, default=24 * 3600)
    parser.add_argument("--server-start-timeout", type=float, default=600)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    model_root = Path(args.model_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    missing = [
        f"{item['model_id']} ({model_root / str(item['local_dir'])})"
        for item in manifest["models"]
        if not (model_root / str(item["local_dir"])).is_dir()
    ]
    if missing and not args.allow_missing:
        raise FileNotFoundError(
            "missing weights; refusing to start a partial ablation: "
            + ", ".join(missing)
        )
    summary: Dict[str, Any] = {
        "manifest": str(manifest_path),
        "selection_split": manifest["selection_split"],
        "models": [],
    }

    for index, model in enumerate(manifest["models"]):
        local_path = model_root / str(model["local_dir"])
        entry: Dict[str, Any] = {**model, "local_path": str(local_path)}
        if not local_path.is_dir():
            entry["status"] = "missing_weights"
            summary["models"].append(entry)
            if not args.allow_missing:
                raise FileNotFoundError(
                    f"missing weights for {model['model_id']}: {local_path}; "
                    "download them or pass --allow-missing"
                )
            continue

        safe_name = str(model["local_dir"]).replace("/", "_")
        model_output = output_root / f"{index:02d}_{safe_name}.json"
        server_log = output_root / f"{index:02d}_{safe_name}.server.log"
        run_log = output_root / f"{index:02d}_{safe_name}.run.log"
        health_endpoint = f"http://127.0.0.1:{args.privacy_port}"
        endpoint = health_endpoint + "/v1"
        server_name = f"local-privacy-{safe_name}"
        with server_log.open("wb") as server_stream:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    "benchmarks/serve_transformers_openai.py",
                    "--model",
                    str(local_path),
                    "--device",
                    args.device,
                    "--served-model-name",
                    server_name,
                    "--max-output-tokens",
                    "256",
                    "--format-guard",
                    "--json-grammar",
                    "--port",
                    str(args.privacy_port),
                ],
                stdout=server_stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        try:
            wait_health(health_endpoint, server, args.server_start_timeout)
            command = [
                sys.executable,
                "-u",
                "-m",
                "benchmarks.run_nlpcc_real",
                "--nlpcc-root",
                args.nlpcc_root,
                "--model",
                args.task_model,
                "--model-base-url",
                args.task_model_base_url,
                "--privacy-model-base-url",
                endpoint,
                "--privacy-model-name",
                server_name,
                "--max-days",
                str(args.development_days),
                "--methods",
                "finscope",
                "--output",
                str(model_output),
            ]
            with run_log.open("wb") as run_stream:
                completed = subprocess.run(
                    command,
                    stdout=run_stream,
                    stderr=subprocess.STDOUT,
                    timeout=args.run_timeout,
                    check=False,
                )
            entry["status"] = "completed" if completed.returncode == 0 else "failed"
            entry["returncode"] = completed.returncode
            entry["result"] = str(model_output)
            if completed.returncode == 0:
                entry["metrics"] = summarize_result(
                    json.loads(model_output.read_text(encoding="utf-8"))
                )
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            stop_process(server)
        summary["models"].append(entry)
        (output_root / "summary.partial.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    output = output_root / "summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
