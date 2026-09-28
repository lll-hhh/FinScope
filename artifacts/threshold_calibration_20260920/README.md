# Qwen3.5-4B Threshold Calibration (Real Run)

This directory contains the real development-run artifacts used to freeze the
FinScope replacement threshold on 2026-09-22. These files are not simulated.

## Decision

- Task model: Qwen3.8-27B
- Local privacy agent and zero-shot attacker: Qwen3.5-4B
- Benchmark: StockBench development interval requested as 2025-03-03 through
  2025-03-28
- Public prior used for selection: K4
- Candidate set: `T={0.20, 0.40, 0.60, 0.80}`
- Utility constraint: maximum loss at most 5% relative to Episode Alias
- Frozen result: `T=0.40`

| T | Utility loss | Eligible | ReID@1 | Link AUC | Privacy risk |
| ---: | ---: | :---: | ---: | ---: | ---: |
| 0.20 | 0.0000 | yes | 0.725 | 0.6694 | 0.7250 |
| 0.40 | 0.0000 | yes | 0.600 | 0.5689 | 0.6000 |
| 0.60 | 0.0884 | no | 0.675 | 0.8007 | 0.6750 |
| 0.80 | 0.0000 | yes | 0.775 | 0.8850 | 0.7750 |

`Privacy risk = max(ReID@1, 2 * abs(Link AUC - 0.5))`. The selector first
rejects ineligible policies and then minimizes privacy risk. Therefore 0.40 is
selected rather than assumed.

## Contents

- `calibration/`: frozen T, empirical K4 lookup, utility sweep and complete
  calibration object.
- `raw/dev_probe_llm_attack.json`: full K1-K4, multi-length public-prior attack
  output used to construct the lookup.
- `raw/candidates/`: each candidate's K4 attack result and proxy log.
- `reports/`: the exact StockBench `metrics.json`, summary and metadata selected
  by the utility builder for the reference and four candidates.
- `logs/`: completion logs for the resumed calibration stage.
- `SHA256SUMS`: integrity hashes relative to the repository checkout where the
  manifest was generated.

Prompt-input audits and source `audit.jsonl` trajectories are intentionally
excluded. The latter contain local alias-to-canonical bindings, which must not
be published even though this run used public securities. They remain in the
restricted experiment workspace and can be regenerated from the benchmark,
code, configuration and seed. All resulting scores, confidence intervals,
per-target attack predictions and StockBench metrics used by the selector are
included. Model weights and external benchmark datasets are also excluded.

## Important limitation

The StockBench metric files used by this run report `n=4` NAV observations,
despite the requested development interval. This package exactly reproduces
the completed selection, but the result must not be presented as final paper
statistics until the new server verifies the StockBench calendar/reporting
path and reruns the development-only calibration if the interval was truncated.
The test split must never be used to change T.

Verify the package with:

```bash
sha256sum -c artifacts/threshold_calibration_20260920/SHA256SUMS
```
