# FinScope × NLPCC2026 Task 4 — Main Experiment

- Track: macro
- Period: 2025-01-02 to 2025-12-31 (243 trading days)
- News setting: top-rank=2 (research main experiment; not an official Top-20 leaderboard score)
- Model: Qwen/Qwen3-8B, 32K context

| Condition | Days | Trade days | Return | Sharpe | MaxDD | Exec rate | Proxy errors | ETF exposure | Aliases | Prompt tok | Completion tok | Mean latency s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| original | 243 | 239 | 23.7748% | 1.9063 | -6.4239% | 83.7116% | 0 | 100.0000% | 0 | 9547533 | 735229 | 2.3015 |
| direct | 243 | 242 | 33.0146% | 1.9457 | -7.8722% | 84.7118% | 0 | 0.0000% | 22809 | 9607226 | 727898 | 2.2436 |
| finscope | 243 | 242 | 34.5010% | 2.2858 | -5.1400% | 87.5164% | 0 | 0.6810% | 22169 | 9648496 | 742117 | 2.1142 |

## Integrity checks

- original: days=243, requests=11192, successful=11192, errors=0, attempted trades=749, executed=627, rejected=122.
- direct: days=243, requests=11192, successful=11192, errors=0, attempted trades=798, executed=676, rejected=122.
- finscope: days=243, requests=11192, successful=11192, errors=0, attempted trades=761, executed=666, rejected=95.
