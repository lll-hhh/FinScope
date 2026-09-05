#!/usr/bin/env bash
set -Eeuo pipefail

# Sequential queue for the strict Qwen3.8-27B runs.  The local model
# selection is performed first; all later stages use the selected model.
ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
NLPCC_ROOT=${NLPCC_ROOT:-/home/zgx/data/nlpcc2026_20260818}
TASK_MODEL=${TASK_MODEL:-/home/zgx/models/Qwen3.8-27B}
TASK_MODEL_NAME=${TASK_MODEL_NAME:-Qwen3.8-27B}
QUEUE_ROOT=${QUEUE_ROOT:-/home/zgx/runlogs/finscope_qwen_20260826}
SELECT_ROOT=${SELECT_ROOT:-$QUEUE_ROOT/local_model_selection}
PRIVACY_PORT=${PRIVACY_PORT:-8120}
PRIVACY_URL=${PRIVACY_URL_OVERRIDE:-"http://127.0.0.1:${PRIVACY_PORT}/v1"}
PRIVACY_NAME=${PRIVACY_NAME:-selected-local-privacy}
PRIVACY_TAG=${PRIVACY_TAG:-qwen25_3b}
EXTERNAL_ROOT=${EXTERNAL_ROOT:-$QUEUE_ROOT/selected_external_matrix}
NLPCC_OUT=${NLPCC_OUT:-$QUEUE_ROOT/nlpcc_selected_local}
LOCAL_PRIVACY_MODEL_PATH=${LOCAL_PRIVACY_MODEL_PATH:-}
LOCAL_PRIVACY_MODEL_ID=${LOCAL_PRIVACY_MODEL_ID:-}
LOCAL_PRIVACY_MODEL_NAME=${LOCAL_PRIVACY_MODEL_NAME:-}
LOCAL_PRIVACY_PARAMETERS_B=${LOCAL_PRIVACY_PARAMETERS_B:-3.0}

mkdir -p "$QUEUE_ROOT" "$NLPCC_OUT" "$EXTERNAL_ROOT" "$ROOT/artifacts"
exec > >(tee -a "$QUEUE_ROOT/followup_queue.log") 2>&1

wait_for_file() {
  local path=$1
  while [[ ! -f "$path" ]]; do
    sleep 30
  done
}

wait_health() {
  local url=$1
  for _ in $(seq 1 120); do
    if curl -fsS --max-time 3 "$url/health" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "health check failed: $url" >&2
  return 1
}

select_model() {
  # The current study protocol fixes the local privacy Agent model. This
  # branch is deliberately before the historical ten-model selector so an
  # old Llama result cannot silently become the formal model again.
  if [[ -n "$LOCAL_PRIVACY_MODEL_PATH" ]]; then
    [[ -f "$LOCAL_PRIVACY_MODEL_PATH/config.json" ]] || {
      echo "missing fixed local privacy model: $LOCAL_PRIVACY_MODEL_PATH" >&2
      return 1
    }
    if ! find "$LOCAL_PRIVACY_MODEL_PATH" -maxdepth 1 -type f \
      \( -name '*.safetensors' -o -name '*.bin' -o -name '*.pt' \) \
      -size +1M | grep -q .; then
      echo "fixed local privacy model has no completed weight shard: $LOCAL_PRIVACY_MODEL_PATH" >&2
      return 1
    fi
    "$PYTHON" - "$QUEUE_ROOT/selected_model.json" <<'PY'
import json, os, pathlib, sys
payload = {
    "selection_rule": "fixed by study protocol",
    "model_id": os.environ.get("LOCAL_PRIVACY_MODEL_ID") or "Qwen/Qwen2.5-3B-Instruct",
    "model_name": os.environ.get("LOCAL_PRIVACY_MODEL_NAME") or "Qwen2.5-3B-Instruct",
    "local_path": os.environ["LOCAL_PRIVACY_MODEL_PATH"],
    "parameters_b": float(os.environ.get("LOCAL_PRIVACY_PARAMETERS_B") or 3.0),
    "fallback_allowed": True,
}
payload["chosen"] = dict(payload)
pathlib.Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
PY
    return 0
  fi
  local summary="$SELECT_ROOT/summary.json"
  wait_for_file "$summary"
  "$PYTHON" - "$summary" "$QUEUE_ROOT/selected_model.json" <<'PY'
import json, pathlib, sys

summary = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = [row for row in summary.get("models", []) if row.get("status") == "completed"]
def metric(row, key, default=float("inf")):
    value = (row.get("metrics") or {}).get(key)
    return default if value is None else float(value)

eligible = [
    row for row in rows
    if metric(row, "strict_planner_valid", -1.0) >= 0.99
    and metric(row, "recognizer_failure_rate", 1.0) == 0.0
    and metric(row, "auditor_failure_rate", 1.0) == 0.0
    and metric(row, "fallback_count", 1.0) == 0.0
]
if not eligible:
    completed = ", ".join(str(row.get("model_id")) for row in rows) or "none"
    raise SystemExit(
        "no strict-eligible local privacy model; refusing to run the Qwen "
        f"benchmark queue (completed: {completed})"
    )
pool = eligible

chosen = sorted(
    pool,
    key=lambda row: (
        -metric(row, "strict_planner_valid", -1.0),
        metric(row, "privacy_agent_p95_ms"),
        metric(row, "privacy_agent_tokens"),
    ),
)[0]
payload = {
    "selection_rule": "strict planner >=99%, zero recognizer/auditor failures and zero fallback; then lowest local p95/tokens",
    "strict_eligible": bool(eligible),
    "chosen": chosen,
    "completed_models": len(rows),
    "manifest_models": len(summary.get("models", [])),
}
pathlib.Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
PY
}

start_privacy_server() {
  local model_path=$1
  local log="$QUEUE_ROOT/selected_privacy_server.log"
  if [[ -n "${PRIVACY_URL_OVERRIDE:-}" ]]; then
    local health_base="${PRIVACY_URL_OVERRIDE%/v1}"
    wait_health "$health_base"
    echo "using pre-existing local privacy service: $PRIVACY_URL_OVERRIDE"
    return 0
  fi
  "$PYTHON" -u "$ROOT/benchmarks/serve_transformers_openai.py" \
    --model "$model_path" --device cuda:4 --served-model-name "$PRIVACY_NAME" \
    --max-output-tokens 512 --format-guard --json-grammar \
    --port "$PRIVACY_PORT" >"$log" 2>&1 &
  PRIVACY_PID=$!
  wait_health "http://127.0.0.1:${PRIVACY_PORT}"
  trap 'kill -TERM "$PRIVACY_PID" 2>/dev/null || true' EXIT
}

run_nlpcc_method() {
  local method=$1 endpoint=$2
  local output="$NLPCC_OUT/${method}.json"
  local log="$NLPCC_OUT/${method}.log"
  local -a extra=()
  if [[ "$method" == "llm_rewrite" ]]; then
    extra=(--rewrite-cache
      "$ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard0.json"
      "$ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard1.json"
      "$ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard2.json")
  fi
  # OpenAIBackend appends /v1 itself; passing /v1 here produced /v1/v1
  # and made otherwise healthy Qwen3.8 requests fail with HTTP 404.
  "$PYTHON" -u -m benchmarks.run_nlpcc_real \
    --nlpcc-root "$NLPCC_ROOT" --model "$TASK_MODEL" \
    --model-base-url "http://127.0.0.1:${endpoint}" \
    --privacy-model-base-url "$PRIVACY_URL" --privacy-model-name "$PRIVACY_NAME" \
    --max-new-tokens 128 --methods "$method" --output "$output" \
    "${extra[@]}" >"$log" 2>&1
}

run_nlpcc() {
  [[ -f "$QUEUE_ROOT/NLPCC_COMPLETE" ]] && return 0
  wait_health http://127.0.0.1:8105
  wait_health http://127.0.0.1:8106
  local methods_a=(vanilla deletion fixed_alias)
  local methods_b=(llm_rewrite episode_alias finscope)
  local pids=()
  for method in "${methods_a[@]}"; do
    run_nlpcc_method "$method" 8105 & pids+=("$!")
  done
  for method in "${methods_b[@]}"; do
    run_nlpcc_method "$method" 8106 & pids+=("$!")
  done
  local failed=0
  for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
  done
  (( failed == 0 )) || { echo "NLPCC stage failed" >&2; return 1; }
  "$PYTHON" -u -m benchmarks.merge_nlpcc_runs \
    "$NLPCC_OUT/vanilla.json" "$NLPCC_OUT/deletion.json" \
    "$NLPCC_OUT/llm_rewrite.json" "$NLPCC_OUT/fixed_alias.json" \
    "$NLPCC_OUT/episode_alias.json" "$NLPCC_OUT/finscope.json" \
    --output "$ROOT/benchmarks/results/nlpcc_qwen38_selected_local_final.json" \
    >"$NLPCC_OUT/merge.log" 2>&1
  date -Is > "$QUEUE_ROOT/NLPCC_COMPLETE"
}

run_external() {
  [[ -f "$QUEUE_ROOT/EXTERNAL_COMPLETE" ]] && return 0
  local pids=()
  RUN_ROOT="$EXTERNAL_ROOT" PRIVACY_TAG="$PRIVACY_TAG" \
    PRIVACY_MODEL_BASE_URL="$PRIVACY_URL" PRIVACY_MODEL_NAME="$PRIVACY_NAME" \
    "$ROOT/benchmarks/run_qwen_external_matrix.sh" lane 5 \
    stockbench:vanilla stockbench:deletion stockbench:llm_rewrite \
    finvault:vanilla finvault:deletion finvault:llm_rewrite & pids+=("$!")
  RUN_ROOT="$EXTERNAL_ROOT" PRIVACY_TAG="$PRIVACY_TAG" \
    PRIVACY_MODEL_BASE_URL="$PRIVACY_URL" PRIVACY_MODEL_NAME="$PRIVACY_NAME" \
    "$ROOT/benchmarks/run_qwen_external_matrix.sh" lane 6 \
    stockbench:global_alias stockbench:episode_alias stockbench:finscope \
    finvault:global_alias finvault:episode_alias finvault:finscope & pids+=("$!")
  local failed=0
  for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
  done
  (( failed == 0 )) || { echo "external stage failed" >&2; return 1; }
  "$PYTHON" -u -m benchmarks.summarize_external_matrix \
    --run-root "$EXTERNAL_ROOT" --stockbench-root /home/zgx/repos/stockbench-src \
    --finvault-root /home/zgx/repos/FinVault-src --results-root "$ROOT/benchmarks/results" \
    --output "$ROOT/artifacts/qwen38_selected_local_external_matrix_final.json" \
    >"$EXTERNAL_ROOT/merge.log" 2>&1
  date -Is > "$QUEUE_ROOT/EXTERNAL_COMPLETE"
}

select_model
model_path=$("$PYTHON" - "$QUEUE_ROOT/selected_model.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print((payload.get("chosen") or payload)["local_path"])
PY
)
echo "selected local model: $model_path"
start_privacy_server "$model_path"
run_nlpcc
run_external
date -Is > "$QUEUE_ROOT/QWEN_EXECUTABLE_QUEUE_COMPLETE"
