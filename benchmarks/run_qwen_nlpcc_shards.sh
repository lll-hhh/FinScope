#!/usr/bin/env bash
set -Eeuo pipefail

FINSCOPE_ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
EXTERNAL_ROOT=${EXTERNAL_ROOT:?EXTERNAL_ROOT is required}
EXTERNAL_SUPERVISOR_PID=${EXTERNAL_SUPERVISOR_PID:?EXTERNAL_SUPERVISOR_PID is required}
RUN_ROOT=${RUN_ROOT:-/home/zgx/runlogs/finscope_qwen_20260823/nlpcc_qwen38_qwen35_2b_final_v1}
OUTPUT_ROOT=${OUTPUT_ROOT:-$FINSCOPE_ROOT/benchmarks/results/nlpcc_qwen38_qwen35_2b_final}
NLPCC_ROOT=${NLPCC_ROOT:-/home/zgx/data/nlpcc2026_20260818}
TASK_MODEL=${TASK_MODEL:-/home/zgx/models/Qwen3.8-27B}
PRIVACY_BASE_URL=${PRIVACY_BASE_URL:-http://127.0.0.1:8112/v1}
PRIVACY_MODEL=${PRIVACY_MODEL:-Qwen3.5-2B}

mkdir -p "$RUN_ROOT" "$OUTPUT_ROOT"

while [[ ! -f "$EXTERNAL_ROOT/ALL_COMPLETE" ]]; do
  if ! kill -0 "$EXTERNAL_SUPERVISOR_PID" 2>/dev/null; then
    echo "external matrix supervisor $EXTERNAL_SUPERVISOR_PID exited without ALL_COMPLETE" >&2
    exit 1
  fi
  sleep 60
done

declare -A ENDPOINT_GPU=(
  [vanilla]=4
  [deletion]=5
  [llm_rewrite]=6
  [fixed_alias]=4
  [episode_alias]=5
  [finscope]=6
)

run_method() {
  local method=$1
  local gpu=${ENDPOINT_GPU[$method]}
  local output="$OUTPUT_ROOT/${method}.json"
  local log="$RUN_ROOT/${method}.run.log"
  local checkpoint="$OUTPUT_ROOT/${method}.json.checkpoint.json"
  local -a extra=()
  if [[ "$method" == "llm_rewrite" ]]; then
    extra=(
      --rewrite-cache
      "$FINSCOPE_ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard0.json"
      "$FINSCOPE_ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard1.json"
      "$FINSCOPE_ROOT/benchmarks/results/nlpcc_qwen38_rewrite_cache_shard2.json"
    )
  fi
  cd "$FINSCOPE_ROOT"
  "$PYTHON" -u -m benchmarks.run_nlpcc_real \
    --nlpcc-root "$NLPCC_ROOT" \
    --model "$TASK_MODEL" \
    --model-base-url "http://127.0.0.1:810${gpu}/v1" \
    --privacy-model-base-url "$PRIVACY_BASE_URL" \
    --privacy-model-name "$PRIVACY_MODEL" \
    --max-new-tokens 128 \
    --methods "$method" \
    --output "$output" \
    --checkpoint "$checkpoint" \
    "${extra[@]}" >"$log" 2>&1
}

for method in vanilla deletion llm_rewrite fixed_alias episode_alias finscope; do
  run_method "$method" &
done
wait

cd "$FINSCOPE_ROOT"
"$PYTHON" -u -m benchmarks.merge_nlpcc_runs \
  "$OUTPUT_ROOT/vanilla.json" \
  "$OUTPUT_ROOT/deletion.json" \
  "$OUTPUT_ROOT/llm_rewrite.json" \
  "$OUTPUT_ROOT/fixed_alias.json" \
  "$OUTPUT_ROOT/episode_alias.json" \
  "$OUTPUT_ROOT/finscope.json" \
  --output "$FINSCOPE_ROOT/benchmarks/results/nlpcc_real_2025_qwen38_qwen35_2b_final.json" \
  >"$RUN_ROOT/merge.log" 2>&1
date -Is >"$RUN_ROOT/ALL_COMPLETE"
