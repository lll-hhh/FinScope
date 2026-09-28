#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
STOCKBENCH_ROOT=${STOCKBENCH_ROOT:-/home/zgx/repos/stockbench-src}
PIPELINE_ROOT=${PIPELINE_ROOT:-/home/zgx/runlogs/finscope_qwen35_4b_20260906/llm_attack_formal_20260920}
ATTACKER_URL=${ATTACKER_URL:-http://127.0.0.1:18002/v1}
ATTACKER_MODEL=${ATTACKER_MODEL:-qwen35_4b}
REPORT_ROOT="$STOCKBENCH_ROOT/storage/reports/backtest"

run_attack() {
  local compact=$1
  local candidate="$PIPELINE_ROOT/candidate_t${compact}"
  local output="$candidate/llm_attack.json"
  [[ -f "$candidate/COMPLETE" ]] || {
    echo "candidate T=$compact is incomplete" >&2
    return 1
  }
  if [[ ! -s "$output" ]]; then
    "$PYTHON" -u -m benchmarks.run_llm_privacy_attacks \
      --benchmark stockbench \
      --audit-dir "$candidate" \
      --benchmark-root "$STOCKBENCH_ROOT" \
      --methods finscope \
      --prior-levels K4 \
      --trace-lengths 0 \
      --attacker-base-url "$ATTACKER_URL" \
      --attacker-model "$ATTACKER_MODEL" \
      --max-identity-targets 40 \
      --max-link-pairs 200 \
      --max-tokens 1536 \
      --output "$output" \
      --prompt-audit "$candidate/llm_attack_prompt_inputs.jsonl"
  fi
}

for compact in 020 040 060 080; do
  run_attack "$compact"
done

UTILITY="$PIPELINE_ROOT/utility_sweep.json"
"$PYTHON" -m benchmarks.build_adaptive_utility_artifact \
  --report-root "$REPORT_ROOT" \
  --reference-run-id qwen38_episode_alias_qwen35_4b_llm_probe_qwen35_4b_llm_probe_dev20 \
  --reference-audit "$PIPELINE_ROOT/dev_probe/stockbench_episode_alias_audit.jsonl" \
  --candidate "0.20:qwen38_finscope_qwen35_4b_llm_t020_qwen35_4b_llm_t020_dev20:$PIPELINE_ROOT/candidate_t020/stockbench_finscope_audit.jsonl" \
  --candidate "0.40:qwen38_finscope_qwen35_4b_llm_t040_qwen35_4b_llm_t040_dev20:$PIPELINE_ROOT/candidate_t040/stockbench_finscope_audit.jsonl" \
  --candidate "0.60:qwen38_finscope_qwen35_4b_llm_t060_qwen35_4b_llm_t060_dev20:$PIPELINE_ROOT/candidate_t060/stockbench_finscope_audit.jsonl" \
  --candidate "0.80:qwen38_finscope_qwen35_4b_llm_t080_qwen35_4b_llm_t080_dev20:$PIPELINE_ROOT/candidate_t080/stockbench_finscope_audit.jsonl" \
  --candidate-attack "0.20:$PIPELINE_ROOT/candidate_t020/llm_attack.json" \
  --candidate-attack "0.40:$PIPELINE_ROOT/candidate_t040/llm_attack.json" \
  --candidate-attack "0.60:$PIPELINE_ROOT/candidate_t060/llm_attack.json" \
  --candidate-attack "0.80:$PIPELINE_ROOT/candidate_t080/llm_attack.json" \
  --output "$UTILITY" \
  --max-utility-loss 0.05

CALIBRATION="$PIPELINE_ROOT/adaptive_calibration_llm.json"
if ! "$PYTHON" -m benchmarks.calibrate_adaptive_policy \
  --attack-artifact "$PIPELINE_ROOT/qwen35_4b_empirical_risk_lookup.json" \
  --utility-artifact "$UTILITY" \
  --max-utility-loss 0.05 \
  --output "$CALIBRATION"; then
  "$PYTHON" -m benchmarks.calibrate_adaptive_policy \
    --attack-artifact "$PIPELINE_ROOT/qwen35_4b_empirical_risk_lookup.json" \
    --utility-artifact "$UTILITY" \
    --max-utility-loss 0.10 \
    --output "$CALIBRATION"
fi

"$PYTHON" - "$CALIBRATION" "$PIPELINE_ROOT/FINAL_T" <<'PY'
import json
import sys
from pathlib import Path

calibration = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
Path(sys.argv[2]).write_text(f"{calibration['threshold']}\n", encoding="utf-8")
PY
date -Is > "$PIPELINE_ROOT/CALIBRATION_COMPLETE"
echo "calibration complete: T=$(cat "$PIPELINE_ROOT/FINAL_T")"
