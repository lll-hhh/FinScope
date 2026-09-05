#!/usr/bin/env bash
set -Eeuo pipefail

# Formal queue using the already-running Qwen3.5-4B local privacy service.
# The endpoint is checked before the queue starts; no model from another
# family can be selected implicitly.
ROOT=${FINSCOPE_ROOT:-/home/zgx/repos/FinScope-git}
MODEL_PATH=${LOCAL_PRIVACY_MODEL_PATH:-/home/zgx/models/Qwen3.5-4B}
MODEL_ID=${LOCAL_PRIVACY_MODEL_ID:-Qwen/Qwen3.5-4B}
MODEL_NAME=${LOCAL_PRIVACY_MODEL_NAME:-qwen35_4b}
MODEL_PARAMETERS_B=${LOCAL_PRIVACY_PARAMETERS_B:-4.0}
QUEUE_ROOT=${QUEUE_ROOT:-/home/zgx/runlogs/finscope_qwen35_4b_20260906}
PRIVACY_URL_OVERRIDE=${PRIVACY_URL_OVERRIDE:-http://127.0.0.1:18002/v1}

[[ -f "$MODEL_PATH/config.json" ]] || {
  echo "missing local privacy model metadata: $MODEL_PATH" >&2
  exit 2
}
if ! find "$MODEL_PATH" -maxdepth 1 -type f \
  \( -name '*.safetensors' -o -name '*.bin' -o -name '*.pt' \) -size +1M | grep -q .; then
  echo "local privacy model has no completed weight shard: $MODEL_PATH" >&2
  exit 2
fi

export LOCAL_PRIVACY_MODEL_PATH="$MODEL_PATH"
export LOCAL_PRIVACY_MODEL_ID="$MODEL_ID"
export LOCAL_PRIVACY_MODEL_NAME="$MODEL_NAME"
export LOCAL_PRIVACY_PARAMETERS_B="$MODEL_PARAMETERS_B"
export PRIVACY_URL_OVERRIDE
export PRIVACY_NAME="$MODEL_NAME"
export PRIVACY_TAG=qwen35_4b
export QUEUE_ROOT
exec "$ROOT/benchmarks/queue_qwen_followup.sh"
