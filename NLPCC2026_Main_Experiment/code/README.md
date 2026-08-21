# NLPCC 2026 Task 4 experiment adapter

This directory evaluates the official multi-agent starter pipeline under three
controlled privacy conditions while leaving the official benchmark code intact.

- `original`: official prompts, unchanged.
- `direct`: globally stable deterministic aliases.
- `finscope`: one typed-alias scope per complete multi-agent decision cycle,
  shared by concurrent news workers, the sentiment agent, and the trading agent;
  aliases rotate before the next official trading day and restore to executable
  exchange-qualified codes locally.

The official agent remains responsible for news summarization, sentiment
analysis, portfolio reasoning, and backtest decisions.  The proxy is only the
trusted boundary around external model calls.

The primary financial metrics are cumulative return plus Sharpe ratio and
maximum drawdown computed from the official daily after-trade snapshots. Proxy
logs add model-call latency, token use, role counts, known-ETF identifier
exposure, alias occurrences, and FinScope lifecycle counters. The exposure
metric covers the official candidate ETF names/codes, not arbitrary entities in
the full news corpus.

Example proxy command from the repository root:

```bash
python NLPCC2026_Main_Experiment/code/privacy_proxy.py \
  --mode finscope \
  --port 8012 \
  --nlpcc-root /private/phx/NLPCC2026-Shared-Task-4/NLPCC_tasks \
  --audit-log /private/phx/FinScope/runs/nlpcc2026/proxy_finscope.jsonl
```

The proxy rewrites the incoming model name to the pinned local model so that
the official starter's hard-coded news model and configurable decision model
use the same reproducible endpoint.
