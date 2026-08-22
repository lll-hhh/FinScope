#!/usr/bin/env bash
set -Eeuo pipefail

FINSCOPE_ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
STOCKBENCH_ROOT=${STOCKBENCH_ROOT:-/home/zgx/repos/stockbench-src}
FINVAULT_ROOT=${FINVAULT_ROOT:-/home/zgx/repos/FinVault-src}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
PRIVACY_TAG=${PRIVACY_TAG:-qwen35_2b}
RUN_ROOT=${RUN_ROOT:-/home/zgx/runlogs/finscope_qwen_20260822/${PRIVACY_TAG}_local_agent_final}
MODEL_NAME=${MODEL_NAME:-Qwen3.8-27B}
PRIVACY_MODEL_BASE_URL=${PRIVACY_MODEL_BASE_URL:-http://127.0.0.1:8112/v1}
PRIVACY_MODEL_NAME=${PRIVACY_MODEL_NAME:-Qwen3.5-2B}

mkdir -p "$RUN_ROOT" "$FINSCOPE_ROOT/benchmarks/results"

health_wait() {
  local port=$1
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "proxy on port ${port} did not become healthy" >&2
  return 1
}

run_stockbench() {
  local method=$1 gpu=$2
  local upstream_port=$((8100 + gpu)) proxy_port=$((8200 + gpu))
  local run_id="qwen38_${method}_${PRIVACY_TAG}_privacy_full_20250303_20250731_final"
  local audit="$RUN_ROOT/stockbench_${method}_audit.jsonl"
  local proxy_log="$RUN_ROOT/stockbench_${method}_proxy.log"
  local task_log="$RUN_ROOT/stockbench_${method}.log"
  rm -f "$audit"

  local cache_mode
  cache_mode=$(cd "$STOCKBENCH_ROOT" && "$PYTHON" -c \
    'import yaml; print(yaml.safe_load(open("config.yaml", encoding="utf-8-sig"))["cache"]["mode"])')
  if [[ "$cache_mode" != "off" ]]; then
    echo "StockBench cache.mode must be the quoted string \"off\"; got: $cache_mode" >&2
    return 2
  fi

  cd "$FINSCOPE_ROOT"
  "$PYTHON" -u -m benchmarks.serve_privacy_proxy \
    --benchmark stockbench --method "$method" \
    --upstream-url "http://127.0.0.1:${upstream_port}/v1" \
    --upstream-model "$MODEL_NAME" --audit-log "$audit" \
    --privacy-model-base-url "$PRIVACY_MODEL_BASE_URL" \
    --privacy-model-name "$PRIVACY_MODEL_NAME" \
    --port "$proxy_port" >"$proxy_log" 2>&1 &
  local proxy_pid=$!
  trap 'kill -TERM "$proxy_pid" 2>/dev/null || true' RETURN
  health_wait "$proxy_port"

  cd "$STOCKBENCH_ROOT"
  "$PYTHON" -u -m stockbench.apps.run_backtest \
    --cfg config.yaml --start 2025-03-03 --end 2025-07-31 \
    --llm-profile "qwen-proxy${gpu}" --agent-mode dual --offline \
    --no-summary-llm --run-id "$run_id" >"$task_log" 2>&1
  kill -TERM "$proxy_pid" 2>/dev/null || true
  wait "$proxy_pid" 2>/dev/null || true
  trap - RETURN
  printf 'completed stockbench %s on gpu %s\n' "$method" "$gpu"
}

run_finvault() {
  local method=$1 gpu=$2
  local upstream_port=$((8100 + gpu)) proxy_port=$((8300 + gpu))
  local audit="$RUN_ROOT/finvault_${method}_audit.jsonl"
  local proxy_log="$RUN_ROOT/finvault_${method}_proxy.log"
  local attack_log="$RUN_ROOT/finvault_${method}_attacks.log"
  local normal_log="$RUN_ROOT/finvault_${method}_normal.log"
  local attack_output="$FINSCOPE_ROOT/benchmarks/results/finvault_qwen38_${method}_${PRIVACY_TAG}_privacy_attacks_final.json"
  local normal_output="$FINSCOPE_ROOT/benchmarks/results/finvault_qwen38_${method}_${PRIVACY_TAG}_privacy_normal_final.json"
  rm -f "$audit"

  cd "$FINSCOPE_ROOT"
  "$PYTHON" -u -m benchmarks.serve_privacy_proxy \
    --benchmark finvault --benchmark-root "$FINVAULT_ROOT" --method "$method" \
    --upstream-url "http://127.0.0.1:${upstream_port}/v1" \
    --upstream-model "$MODEL_NAME" --audit-log "$audit" \
    --privacy-model-base-url "$PRIVACY_MODEL_BASE_URL" \
    --privacy-model-name "$PRIVACY_MODEL_NAME" \
    --port "$proxy_port" >"$proxy_log" 2>&1 &
  local proxy_pid=$!
  trap 'kill -TERM "$proxy_pid" 2>/dev/null || true' RETURN
  health_wait "$proxy_port"

  cd "$FINVAULT_ROOT"
  env QWEN_LOCAL_BASE_URL="http://127.0.0.1:${proxy_port}/v1/chat/completions" \
    QWEN_LOCAL_MODEL_NAME="$MODEL_NAME" QWEN_LOCAL_API_KEY=local \
    "$PYTHON" -u sandbox/run_attack_test.py --all --agent qwen_chat \
    --mode base --max-turns 10 --concurrency 4 \
    --output "$attack_output" >"$attack_log" 2>&1

  cd "$FINSCOPE_ROOT"
  env QWEN_LOCAL_BASE_URL="http://127.0.0.1:${proxy_port}/v1/chat/completions" \
    QWEN_LOCAL_MODEL_NAME="$MODEL_NAME" QWEN_LOCAL_API_KEY=local \
    "$PYTHON" -u benchmarks/run_finvault_normal.py \
    --finvault-root "$FINVAULT_ROOT" --agent qwen_chat --mode base \
    --max-turns 10 --concurrency 4 --output "$normal_output" \
    >"$normal_log" 2>&1
  kill -TERM "$proxy_pid" 2>/dev/null || true
  wait "$proxy_pid" 2>/dev/null || true
  trap - RETURN
  printf 'completed finvault %s on gpu %s\n' "$method" "$gpu"
}

run_lane() {
  local gpu=$1
  shift
  for task in "$@"; do
    local benchmark=${task%%:*}
    local method=${task#*:}
    case "$benchmark" in
      stockbench) run_stockbench "$method" "$gpu" ;;
      finvault) run_finvault "$method" "$gpu" ;;
      *) echo "unknown benchmark task: $task" >&2; return 2 ;;
    esac
  done
}

case "${1:-}" in
  lane)
    gpu=${2:?GPU index required}
    shift 2
    run_lane "$gpu" "$@"
    ;;
  all)
    "$0" lane 4 stockbench:llm_rewrite stockbench:finscope \
      finvault:llm_rewrite finvault:finscope >"$RUN_ROOT/lane4.log" 2>&1 &
    lane4=$!
    "$0" lane 5 stockbench:deletion stockbench:episode_alias \
      finvault:deletion finvault:episode_alias >"$RUN_ROOT/lane5.log" 2>&1 &
    lane5=$!
    "$0" lane 6 stockbench:global_alias \
      finvault:vanilla finvault:global_alias >"$RUN_ROOT/lane6.log" 2>&1 &
    lane6=$!
    wait "$lane4" "$lane5" "$lane6"
    mkdir -p "$FINSCOPE_ROOT/artifacts"
    "$PYTHON" -m benchmarks.summarize_external_matrix \
      --run-root "$RUN_ROOT" --stockbench-root "$STOCKBENCH_ROOT" \
      --finvault-root "$FINVAULT_ROOT" \
      --results-root "$FINSCOPE_ROOT/benchmarks/results" \
      --output "$FINSCOPE_ROOT/artifacts/qwen38_${PRIVACY_TAG}_external_matrix_final.json"
    "$PYTHON" -m benchmarks.finalize_qwen_external_matrix \
      --summary "$FINSCOPE_ROOT/artifacts/qwen38_${PRIVACY_TAG}_external_matrix_final.json" \
      --document "$FINSCOPE_ROOT/docs/coling_story_experiment_tables.md"
    date -Is >"$RUN_ROOT/ALL_COMPLETE"
    ;;
  *)
    echo "usage: $0 all | lane GPU benchmark:method [...]" >&2
    exit 2
    ;;
esac
