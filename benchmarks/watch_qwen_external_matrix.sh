#!/usr/bin/env bash
set -Eeuo pipefail

FINSCOPE_ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
STOCKBENCH_ROOT=${STOCKBENCH_ROOT:-/home/zgx/repos/stockbench-src}
FINVAULT_ROOT=${FINVAULT_ROOT:-/home/zgx/repos/FinVault-src}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}
RUN_ROOT=${RUN_ROOT:-/home/zgx/runlogs/finscope_qwen_20260822/full_matrix}
GIT_BIN=${GIT_BIN:-/home/zgx/.local/usr/bin/git}
GIT_EXEC_PATH=${GIT_EXEC_PATH:-/home/zgx/.local/usr/lib/git-core}
SUPERVISOR_PID=${SUPERVISOR_PID:?SUPERVISOR_PID is required}

while [[ ! -f "$RUN_ROOT/ALL_COMPLETE" ]]; do
  if ! kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
    echo "matrix supervisor $SUPERVISOR_PID exited without ALL_COMPLETE" >&2
    exit 1
  fi
  sleep 60
done

cd "$FINSCOPE_ROOT"
mkdir -p artifacts
"$PYTHON" -m benchmarks.summarize_external_matrix \
  --run-root "$RUN_ROOT" --stockbench-root "$STOCKBENCH_ROOT" \
  --finvault-root "$FINVAULT_ROOT" --results-root benchmarks/results \
  --output artifacts/qwen38_external_matrix_final.json
"$PYTHON" -m benchmarks.finalize_qwen_external_matrix \
  --summary artifacts/qwen38_external_matrix_final.json \
  --document docs/coling_story_experiment_tables.md

GIT_EXEC_PATH="$GIT_EXEC_PATH" "$GIT_BIN" add \
  artifacts/qwen38_external_matrix_final.json \
  docs/coling_story_experiment_tables.md
if ! GIT_EXEC_PATH="$GIT_EXEC_PATH" "$GIT_BIN" diff --cached --quiet; then
  GIT_EXEC_PATH="$GIT_EXEC_PATH" "$GIT_BIN" commit \
    -m "Publish completed Qwen external matrix"
  GIT_EXEC_PATH="$GIT_EXEC_PATH" "$GIT_BIN" push origin main
fi
