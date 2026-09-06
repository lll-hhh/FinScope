#!/usr/bin/env bash
set -Eeuo pipefail

# Formal, development-only calibration pipeline for the Qwen3.5-4B attacker.
# It starts only after the already-running baseline matrix releases GPUs 4-6,
# so latency measurements from either experiment are not contaminated.
ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
STOCKBENCH_ROOT=${STOCKBENCH_ROOT:-/home/zgx/repos/stockbench-src}
FINVAULT_ROOT=${FINVAULT_ROOT:-/home/zgx/repos/FinVault-src}
NLPCC_ROOT=${NLPCC_ROOT:-/home/zgx/data/nlpcc2026_20260818}
BASE=${BASE:-/home/zgx/runlogs/finscope_qwen35_4b_20260906}
CURRENT_FULL=${CURRENT_FULL:-$BASE/external_full}
BASELINES_READY=${BASELINES_READY:-$CURRENT_FULL/LLM_REWRITE_RERUN_COMPLETE}
PIPELINE_ROOT=${PIPELINE_ROOT:-$BASE/llm_attack_formal}
PRIVACY_URL=${PRIVACY_URL:-http://127.0.0.1:18002/v1}
PRIVACY_MODEL=${PRIVACY_MODEL:-qwen35_4b}
ATTACK_COMMON=(
  --attacker-base-url "$PRIVACY_URL"
  --attacker-model "$PRIVACY_MODEL"
  --max-identity-targets 40
  --max-link-pairs 200
)
mkdir -p "$PIPELINE_ROOT"

run_stock_lane() {
  local run_root=$1 method=$2 gpu=$3 tag=$4 threshold=$5 calibration=${6:-}
  mkdir -p "$run_root"
  RUN_ROOT="$run_root" PRIVACY_TAG="$tag" \
    PRIVACY_MODEL_BASE_URL="$PRIVACY_URL" PRIVACY_MODEL_NAME="$PRIVACY_MODEL" \
    ADAPTIVE_THRESHOLD="$threshold" ADAPTIVE_CALIBRATION="$calibration" \
    STOCKBENCH_START=2025-03-03 STOCKBENCH_END=2025-03-28 \
    STOCKBENCH_RUN_SUFFIX="${tag}_dev20" \
    "$ROOT/benchmarks/run_qwen_external_matrix.sh" lane "$gpu" "stockbench:$method"
}

run_attack() {
  local audit_root=$1 output=$2
  shift 2
  "$PYTHON" -u -m benchmarks.run_llm_privacy_attacks \
    --benchmark stockbench --audit-dir "$audit_root" \
    --benchmark-root "$STOCKBENCH_ROOT" "$@" \
    --prior-levels K1 K2 K3 K4 --trace-lengths 1 5 20 0 \
    "${ATTACK_COMMON[@]}" --output "$output" \
    --prompt-audit "${output%.json}_prompt_inputs.jsonl"
}

if [[ ! -f "$BASELINES_READY" ]]; then
  echo "waiting for isolated GPU lanes: $BASELINES_READY"
  while [[ ! -f "$BASELINES_READY" ]]; do sleep 60; done
fi

DEV_ROOT="$PIPELINE_ROOT/dev_probe"
if [[ ! -f "$DEV_ROOT/COMPLETE" ]]; then
  run_stock_lane "$DEV_ROOT" global_alias 4 qwen35_4b_llm_probe 1.10 & p4=$!
  run_stock_lane "$DEV_ROOT" episode_alias 5 qwen35_4b_llm_probe 1.10 & p5=$!
  run_stock_lane "$DEV_ROOT" finscope 6 qwen35_4b_llm_probe 1.10 & p6=$!
  wait "$p4" "$p5" "$p6"
  date -Is > "$DEV_ROOT/COMPLETE"
fi

INITIAL_ATTACK="$PIPELINE_ROOT/dev_probe_llm_attack.json"
run_attack "$DEV_ROOT" "$INITIAL_ATTACK" \
  --methods fixed_alias episode_alias finscope

RISK_ARTIFACT="$PIPELINE_ROOT/qwen35_4b_risk_estimator.json"
"$PYTHON" -m benchmarks.build_llm_risk_artifact \
  --attack "$INITIAL_ATTACK" --method finscope --output "$RISK_ARTIFACT"

run_candidate() {
  local threshold=$1 gpu=$2
  local compact=${threshold/./}
  local target="$PIPELINE_ROOT/candidate_t${compact}"
  if [[ ! -f "$target/COMPLETE" ]]; then
    run_stock_lane "$target" finscope "$gpu" "qwen35_4b_llm_t${compact}" \
      "$threshold" "$RISK_ARTIFACT"
    date -Is > "$target/COMPLETE"
  fi
  run_attack "$target" "$target/llm_attack.json" --methods finscope
}

run_candidate 0.20 4 & c20=$!
run_candidate 0.40 5 & c40=$!
run_candidate 0.60 6 & c60=$!
wait "$c20" "$c40" "$c60"
run_candidate 0.80 4

UTILITY="$PIPELINE_ROOT/utility_sweep.json"
"$PYTHON" -m benchmarks.build_adaptive_utility_artifact \
  --report-root "$STOCKBENCH_ROOT/storage/reports/backtest" \
  --reference-run-id qwen38_episode_alias_qwen35_4b_llm_probe_qwen35_4b_llm_probe_dev20 \
  --reference-audit "$DEV_ROOT/stockbench_episode_alias_audit.jsonl" \
  --candidate "0.20:qwen38_finscope_qwen35_4b_llm_t020_qwen35_4b_llm_t020_dev20:$PIPELINE_ROOT/candidate_t020/stockbench_finscope_audit.jsonl" \
  --candidate "0.40:qwen38_finscope_qwen35_4b_llm_t040_qwen35_4b_llm_t040_dev20:$PIPELINE_ROOT/candidate_t040/stockbench_finscope_audit.jsonl" \
  --candidate "0.60:qwen38_finscope_qwen35_4b_llm_t060_qwen35_4b_llm_t060_dev20:$PIPELINE_ROOT/candidate_t060/stockbench_finscope_audit.jsonl" \
  --candidate "0.80:qwen38_finscope_qwen35_4b_llm_t080_qwen35_4b_llm_t080_dev20:$PIPELINE_ROOT/candidate_t080/stockbench_finscope_audit.jsonl" \
  --candidate-attack "0.20:$PIPELINE_ROOT/candidate_t020/llm_attack.json" \
  --candidate-attack "0.40:$PIPELINE_ROOT/candidate_t040/llm_attack.json" \
  --candidate-attack "0.60:$PIPELINE_ROOT/candidate_t060/llm_attack.json" \
  --candidate-attack "0.80:$PIPELINE_ROOT/candidate_t080/llm_attack.json" \
  --output "$UTILITY" --max-utility-loss 0.05

CALIBRATION="$PIPELINE_ROOT/adaptive_calibration_llm.json"
if ! "$PYTHON" -m benchmarks.calibrate_adaptive_policy \
  --attack-artifact "$RISK_ARTIFACT" --utility-artifact "$UTILITY" \
  --max-utility-loss 0.05 --output "$CALIBRATION"; then
  "$PYTHON" -m benchmarks.calibrate_adaptive_policy \
    --attack-artifact "$RISK_ARTIFACT" --utility-artifact "$UTILITY" \
    --max-utility-loss 0.10 --output "$CALIBRATION"
fi
T=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["threshold"])' "$CALIBRATION")
printf '%s\n' "$T" > "$PIPELINE_ROOT/FINAL_T"
date -Is > "$PIPELINE_ROOT/CALIBRATION_COMPLETE"

echo "formal LLM-attacker calibration complete: T=$T"

FULL_ROOT="$PIPELINE_ROOT/exact_full"
run_full_lane() {
  local method=$1 gpu=$2
  RUN_ROOT="$FULL_ROOT" PRIVACY_TAG=qwen35_4b_llm_final \
    PRIVACY_MODEL_BASE_URL="$PRIVACY_URL" PRIVACY_MODEL_NAME="$PRIVACY_MODEL" \
    ADAPTIVE_THRESHOLD="$T" ADAPTIVE_CALIBRATION="$CALIBRATION" \
    STOCKBENCH_START=2025-03-03 STOCKBENCH_END=2025-07-31 \
    STOCKBENCH_RUN_SUFFIX=privacy_full_llm_calibrated \
    "$ROOT/benchmarks/run_qwen_external_matrix.sh" lane "$gpu" \
    "stockbench:$method" "finvault:$method"
}

mkdir -p "$FULL_ROOT"
if [[ ! -f "$FULL_ROOT/TRAJECTORIES_COMPLETE" ]]; then
  run_full_lane finscope 4 > "$FULL_ROOT/lane4.log" 2>&1 & f4=$!
  run_full_lane episode_alias 5 > "$FULL_ROOT/lane5.log" 2>&1 & f5=$!
  run_full_lane global_alias 6 > "$FULL_ROOT/lane6.log" 2>&1 & f6=$!
  wait "$f4" "$f5" "$f6"
  date -Is > "$FULL_ROOT/TRAJECTORIES_COMPLETE"
fi

STOCK_ATTACK="$FULL_ROOT/stockbench_llm_prior_attack.json"
"$PYTHON" -u -m benchmarks.run_llm_privacy_attacks \
  --benchmark stockbench --audit-dir "$FULL_ROOT" \
  --benchmark-root "$STOCKBENCH_ROOT" \
  --methods fixed_alias episode_alias finscope \
  --prior-levels K1 K2 K3 K4 --trace-lengths 1 5 20 60 0 \
  "${ATTACK_COMMON[@]}" --output "$STOCK_ATTACK" \
  --prompt-audit "$FULL_ROOT/stockbench_llm_prior_prompt_inputs.jsonl"

FINVAULT_ATTACK="$FULL_ROOT/finvault_llm_prior_attack.json"
"$PYTHON" -u -m benchmarks.run_llm_privacy_attacks \
  --benchmark finvault --audit-dir "$FULL_ROOT" \
  --benchmark-root "$FINVAULT_ROOT" \
  --methods fixed_alias episode_alias finscope \
  --prior-levels K1 K2 K3 K4 --trace-lengths 1 5 0 \
  "${ATTACK_COMMON[@]}" --max-candidates 100 \
  --output "$FINVAULT_ATTACK" \
  --prompt-audit "$FULL_ROOT/finvault_llm_prior_prompt_inputs.jsonl"

# Keep utility/cost rows from the already-running baselines and combine them
# with the freshly calibrated protected methods without overwriting either run.
for artifact in \
  stockbench_deletion_audit.jsonl stockbench_llm_rewrite_audit.jsonl \
  finvault_vanilla_audit.jsonl finvault_deletion_audit.jsonl \
  finvault_llm_rewrite_audit.jsonl; do
  if [[ ! -e "$FULL_ROOT/$artifact" && -e "$CURRENT_FULL/$artifact" ]]; then
    ln -s "$CURRENT_FULL/$artifact" "$FULL_ROOT/$artifact"
  fi
done
"$PYTHON" -m benchmarks.summarize_external_matrix \
  --run-root "$FULL_ROOT" --stockbench-root "$STOCKBENCH_ROOT" \
  --finvault-root "$FINVAULT_ROOT" --results-root "$ROOT/benchmarks/results" \
  --output "$FULL_ROOT/external_matrix_summary.json"

NLPCC_RESULT="$ROOT/benchmarks/results/nlpcc_real_2025_qwen38_qwen35_4b_final.json"
if [[ ! -f "$NLPCC_RESULT" ]]; then
  echo "waiting for NLPCC merged result: $NLPCC_RESULT"
  while [[ ! -f "$NLPCC_RESULT" ]]; do sleep 60; done
fi
"$PYTHON" -u -m benchmarks.run_llm_privacy_attacks \
  --benchmark nlpcc --nlpcc-result "$NLPCC_RESULT" \
  --benchmark-root "$NLPCC_ROOT" --methods fixed_alias episode_alias finscope \
  --prior-levels K1 K2 K3 K4 --trace-lengths 1 5 20 60 0 \
  "${ATTACK_COMMON[@]}" \
  --output "$FULL_ROOT/nlpcc_llm_prior_attack.json" \
  --prompt-audit "$FULL_ROOT/nlpcc_llm_prior_prompt_inputs.jsonl"

date -Is > "$PIPELINE_ROOT/ALL_COMPLETE"
echo "formal LLM-attacker prior experiment and protected main-table rows complete"
