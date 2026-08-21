# Real NLPCC 2026 Track 1 Main Table

- Model: `Qwen3.8-27B` (`1098534ab5d7220ea0f4a6b9f07bb03729a79c1d`)
- Window: `2025-01-02` to `2025-12-31` (243 trading days)
- Data: official public NLPCC 2026 Track 1 news and ETF/index prices; current-day close/high/low/return hidden from prompts
- Trading: CNY 100,000 initial capital, daily close execution, 0.01% friction

| Method | Return ↑ | Sharpe ↑ | Sortino ↑ | MDD ↓ | Turnover | Agree w/ Vanilla ↑ | Weight MAE ↓ | Valid ↑ | Executed ↑ | Direct leak ↓ | Cross-day link ↓ | In tok. ↓ | Local p95 ms ↓ | E2E p95 ms ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vanilla | 39.45% | 2.426 | 3.582 | 6.88% | 13.038 | 99.2% | 0.0000 | 99.2% | 98.8% | 100.0% | 100.0% | 4602.6 | 0.05 | 8215.85 |
| deletion | 0.00% | 0.000 | 0.000 | 0.00% | 0.000 | 0.0% | 0.0865 | 0.0% | 0.0% | 0.0% | 0.0% | 4447.3 | 12.24 | 7750.95 |
| fixed_alias | 25.28% | 2.264 | 3.460 | 4.43% | 16.623 | 33.3% | 0.1244 | 97.5% | 97.5% | 0.0% | 100.0% | 4606.9 | 12.70 | 8179.97 |
| finscope | 33.60% | 2.370 | 3.529 | 7.64% | 20.448 | 28.0% | 0.0944 | 96.3% | 95.9% | 0.0% | 0.0% | 5141.5 | 12.88 | 9222.84 |

## Financial Detail

| Method | Final CNY | Ann. return | Ann. vol. | Calmar | Positive days | VaR 95 | CVaR 95 | Best day | Worst day | Max DD duration | Trades | Final cash |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vanilla | 139,453.33 | 41.18% | 14.67% | 5.986 | 56.4% | 1.28% | 2.14% | 2.55% | -5.26% | 59 | 226 | 9,451.74 |
| deletion | 100,000.00 | 0.00% | 0.00% | 0.000 | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% | 0 | 0 | 100,000.00 |
| fixed_alias | 125,282.27 | 26.33% | 10.58% | 5.950 | 55.6% | 0.86% | 1.53% | 2.28% | -3.07% | 53 | 201 | 18,852.60 |
| finscope | 133,595.16 | 35.04% | 13.04% | 4.588 | 58.4% | 1.25% | 1.94% | 3.82% | -3.87% | 59 | 209 | 21,126.49 |

## Continuity And Utility

| Method | Parse success | Valid / parsed | Execute / valid | Interrupted | Asset agree* | Action agree* | Full agree | Weight MAE | Malformed | Audit rejects | Execution rejects |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vanilla | 99.2% | 100.0% | 99.6% | 1.2% | 100.0% | 100.0% | 99.2% | 0.0000 | 2 | 0 | 1 |
| deletion | 100.0% | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0865 | 0 | 0 | 0 |
| fixed_alias | 98.8% | 98.8% | 100.0% | 2.5% | 43.4% | 57.4% | 33.3% | 0.1244 | 3 | 0 | 0 |
| finscope | 97.5% | 98.7% | 99.6% | 4.1% | 35.3% | 57.8% | 28.0% | 0.0944 | 6 | 3 | 1 |

*Asset and action agreement are conditional on both the method and Vanilla producing valid actions; full agreement uses all 243 days.*

## Privacy

| Method | Direct leaks | Direct leak rate | Cross-day unique link |
| --- | ---: | ---: | ---: |
| vanilla | 243 / 243 | 100.0% | 100.0% |
| deletion | 0 / 243 | 0.0% | 0.0% |
| fixed_alias | 0 / 243 | 0.0% | 100.0% |
| finscope | 0 / 243 | 0.0% | 0.0% |

## Cost And Latency

| Method | Total input tok. | Avg input | Input overhead | Avg output | Model avg ms | Model p95 ms | Local avg ms | Local p95 ms | E2E avg ms | E2E p50 ms | E2E p95 ms | Model hours | Output tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vanilla | 1,118,434 | 4602.6 | +0.0% | 79.5 | 6914.10 | 8215.82 | 0.03 | 0.05 | 6914.13 | 6911.69 | 8215.85 | 0.467 | 11.50 |
| deletion | 1,080,685 | 4447.3 | -3.4% | 69.5 | 6371.49 | 7738.84 | 11.89 | 12.24 | 6383.38 | 6236.19 | 7750.95 | 0.430 | 10.91 |
| fixed_alias | 1,119,488 | 4606.9 | +0.1% | 72.6 | 6549.74 | 8167.71 | 12.22 | 12.70 | 6561.95 | 6651.09 | 8179.97 | 0.442 | 11.09 |
| finscope | 1,249,380 | 5141.5 | +11.7% | 95.3 | 8004.64 | 9210.06 | 12.16 | 12.88 | 8016.80 | 8056.94 | 9222.84 | 0.540 | 11.91 |

## Rejection Breakdown

- **vanilla**: `cannot sell an empty holding`: 1; `model output is not parseable JSON`: 2
- **deletion**: `deleted identifier cannot be restored`: 243
- **fixed_alias**: `buy amount must be positive`: 3; `model output is not parseable JSON`: 3
- **finscope**: `cannot sell an empty holding`: 1; `model output is not parseable JSON`: 6; `restoration audit failed: direct_identity_output`: 3

## Not Measured In This Run

Asset-ReID@1/@5, Pool-Recovery F1, Holding-Inference F1, Weight-Inference MAE from an attacker, Cross-Day-Link AUC from an attacker, Action/Intent Inference, Unsafe Repair Rate, monetary API cost, GPU energy, and peak GPU memory.

This is a full-year public A-set replay, not an official NLPCC leaderboard submission. Direct leak checks literal candidate identifiers; semantic re-identification requires a separate attacker experiment.
