#!/usr/bin/env bash
set -Eeuo pipefail

# Formal queue for the current protocol. The local privacy agent is fixed to
# Qwen2.5-3B-Instruct; the old ten-model selector is intentionally bypassed.
ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
MODEL_PATH=${LOCAL_PRIVACY_MODEL_PATH:-/home/zgx/models/Qwen2.5-3B-Instruct}
MODEL_ID=${LOCAL_PRIVACY_MODEL_ID:-Qwen/Qwen2.5-3B-Instruct}
MODEL_NAME=${LOCAL_PRIVACY_MODEL_NAME:-Qwen2.5-3B-Instruct}
QUEUE_ROOT=${QUEUE_ROOT:-/home/zgx/runlogs/finscope_qwen25_3b_20260905}
PRIVACY_PORT=${PRIVACY_PORT:-8120}
PYTHON=${PYTHON:-/home/zgx/venvs/finscope-qwen38/bin/python}

if [[ ! -f "$MODEL_PATH/config.json" ]]; then
  echo "missing local privacy model: $MODEL_PATH" >&2
  exit 2
fi
if ! find "$MODEL_PATH" -maxdepth 1 -type f \( -name '*.safetensors' -o -name '*.bin' -o -name '*.pt' \) -size +1M | grep -q .; then
  echo "local privacy model has no completed weight shard: $MODEL_PATH" >&2
  exit 2
fi

mkdir -p "$QUEUE_ROOT"
export LOCAL_PRIVACY_MODEL_PATH="$MODEL_PATH"
export LOCAL_PRIVACY_MODEL_ID="$MODEL_ID"
export LOCAL_PRIVACY_MODEL_NAME="$MODEL_NAME"
export QUEUE_ROOT
exec "$ROOT/benchmarks/queue_qwen_followup.sh"
