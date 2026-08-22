# External Benchmark Integration

The Qwen external matrix uses the upstream StockBench and FinVault working
copies without vendoring either project. Two small request-boundary changes are
required before running `benchmarks/run_qwen_external_matrix.sh`.

## StockBench

In `stockbench/llm/llm_client.py`, add the following fields to the request body
created by `LLMClient.generate_json`:

```python
body["finscope_role"] = role
if trade_date:
    body["finscope_episode"] = str(trade_date)
```

The proxy consumes and removes these local metadata fields before forwarding
the OpenAI-compatible request. Explicit episode metadata is necessary because
the fundamental-filter prompt can contain historical dates but omit the
current trading day. Filter and decision calls must share the same daily scope.

Define the three local profiles used by the runner in StockBench's
`config.yaml`:

```yaml
llm_profiles:
  qwen-proxy4:
    provider: vllm
    base_url: http://127.0.0.1:8204/v1
    model: Qwen3.8-27B
    auth_required: false
    timeout_sec: 600
  qwen-proxy5:
    provider: vllm
    base_url: http://127.0.0.1:8205/v1
    model: Qwen3.8-27B
    auth_required: false
    timeout_sec: 600
  qwen-proxy6:
    provider: vllm
    base_url: http://127.0.0.1:8206/v1
    model: Qwen3.8-27B
    auth_required: false
    timeout_sec: 600
```

The runner uses `offline_only` data mode. All price and news data must already
exist in StockBench's local cache.

## FinVault

FinVault's `QwenClient.invoke` must send standard OpenAI field names and the
configured output budget:

```python
payload = {
    "model": self.model_name,
    "temperature": kwargs.get("temperature", self.temperature),
    "max_tokens": kwargs.get("max_tokens", self.max_tokens),
    "messages": modified_messages,
}
```

The original code uses `Temperature`, which an OpenAI-compatible service does
not interpret as the sampling field. Omitting `max_tokens` also makes GPU lanes
with different server defaults incomparable.

## Full Qwen Run

Start one Qwen3.8-27B OpenAI-compatible service on each of ports 8104, 8105 and
8106, all with the same 4096-token output ceiling. Then run:

```bash
setsid -f bash benchmarks/run_qwen_external_matrix.sh all \
  > /home/zgx/runlogs/finscope_qwen_20260822/full_matrix/supervisor.log 2>&1
```

The three lanes run the five remaining StockBench methods and all six FinVault
methods. Each FinVault method evaluates the 107 original attacks and the 107
normal tasks. Per-request audit JSONL records outbound leaks, model usage,
rewrite overhead, restoration status, restoration issues, unsafe repair and
end-to-end latency. `ALL_COMPLETE` is written only after every lane succeeds.

The existing completed StockBench Vanilla result is reused for native metrics;
FinVault Vanilla is rerun because benign-task and over-refusal results were not
available in the earlier attack-only artifact.
