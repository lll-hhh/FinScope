# FinScope

FinScope is a local privacy mediation layer for tool-using financial agents. It keeps the original financial agent logic intact while placing a local controller between the agent and an external language model.

The runtime uses two passes:

1. A local security-master/list and the existing scope mapping replace known terms deterministically.
2. A small local model, recommended first as `Qwen3-0.6B`, inspects only the residual text and returns sensitive spans, semantic types, coreference targets, and risk levels. FinScope validates the result, allocates aliases locally, and replaces the returned spans.

The residual model is not called for every message. `ResidualScanPolicy` warms up, records empty scans, and enters cooldown after the residual has stabilized. Cached safe templates are skipped; risk signals, privacy escalation, periodic probes, and `force_model_scan=True` wake the model again. This bounds local inference cost without permanently disabling discovery.

The external model never receives the real-to-alias table. Restoring an output is deterministic and local. Known references such as `该股` or `it` reuse an antecedent's alias when the model identifies the target. Ambiguous surface forms are replaced by span and type, rather than by unsafe global string substitution.

Aliases are stable within one `(task_id, conversation_id, trading_day)` scope. A new conversation, task completion, or trading-day rotation clears the mapping. Adaptive privacy protection escalates monotonically when portfolio state, execution state, prompt-injection markers, or cumulative disclosure are detected.

## Quick start

```python
from finscope import FinScopeMediator, PrivacyLevel

mediator = FinScopeMediator(
    [{"name": "Apple Inc.", "aliases": ["AAPL"]}]
)
scope = mediator.open_scope(
    "rebalance-42",
    "2026-08-15",
    conversation_id="research-risk-trade",
    privacy_level=PrivacyLevel.STANDARD,
)

safe_prompt = mediator.sanitize_prompt("研究 AAPL 的持仓风险", scope)
external_output = external_llm(safe_prompt)
local_output = mediator.restore_output(external_output, scope)
```

For long-running agents, inspect `mediator.get_privacy_status(scope)` for scan skips, empty scans, and probe counters. Use `force_model_scan=True` after a known market-data refresh or when an adapter receives a new data source.

For local model inference, see `docs/finscope_quickstart.md` and `examples/finscope_local_model_demo.py`. The Transformers integration is lazy; the base package itself has no third-party runtime dependency.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
