# FinScope Server Migration Handoff

This is the authoritative continuation state as of 2026-09-28. Read
`docs/experiment_mainline.md` first for the frozen research story and use this
file for execution status. Older Qwen2.5-3B and trained-risk-estimator notes are
historical and must not override this handoff.

## Current research protocol

FinScope is a trusted local privacy agent for long-horizon financial agents.
It keeps real assets, holdings and orders local; exports scoped semantic
handles; maintains the same protected entity across research, risk and trading
agents; restores exact local objects before execution; and rotates handles when
empirical disclosure risk reaches a calibrated threshold.

- External task model: Qwen3.8-27B for the current Qwen rows.
- Local privacy agent: Qwen3.5-4B.
- Privacy attacker: the same Qwen3.5-4B in zero-shot, temperature-zero mode.
- Risk mechanism: deterministic empirical lookup from K4 attack outcomes. No
  classifier, regression model, Ridge model or risk-estimator training.
- Dynamic disclosure: P1-P5 chooses how much task semantics is exported.
- Replacement threshold: T chooses when the scoped handle is rotated. P-level
  and T are separate controls.
- Frozen development result: `T=0.40` under the 5% utility-loss constraint.

## What is complete

1. Local dual-state implementation: exposure state plus pending task
   dependency state.
2. P1-P5 disclosure, scoped mapping, exact restoration, safe-checkpoint
   replacement and execution validation.
3. Training-free StockBench K1-K4 public-prior attack: 48/48 cells completed
   with zero failed attacker calls.
4. Four complete T candidate trajectories and K4 attacks.
5. Development selector output and frozen calibration artifact.
6. Regression tests for empirical lookup, delayed replacement, JSON response
   restoration, canonical-wrapper removal and handle typo repair.

The exact real artifacts are under
`artifacts/threshold_calibration_20260920/`. The compact selection is:

| T | Utility loss | Eligible | ReID@1 | Link AUC | Decision |
| ---: | ---: | :---: | ---: | ---: | --- |
| 0.20 | 0.0000 | yes | 0.725 | 0.6694 | reject: higher risk |
| 0.40 | 0.0000 | yes | 0.600 | 0.5689 | selected |
| 0.60 | 0.0884 | no | 0.675 | 0.8007 | reject: utility constraint |
| 0.80 | 0.0000 | yes | 0.775 | 0.8850 | reject: higher risk |

## What is not complete

- The full six-method main tables for StockBench, NLPCC and FinVault are not
  complete under the frozen Qwen3.5-4B/T=0.40 protocol.
- DeepSeek V4 Flash and GLM-5.1 rows have not been run under this protocol.
- Fixed-period replacement, replacement timing, component ablation, local
  model selection and fault-safety tables remain follow-up experiments.
- The current calibration's StockBench reports contain only `n=4` NAV points.
  Diagnose the calendar/report generation before treating T=0.40 as a paper
  final. If it is a truncated-development bug, rerun only the development
  calibration, version the artifact and freeze the corrected T before tests.

## New-server bootstrap

```bash
git clone https://github.com/lll-hhh/FinScope.git
cd FinScope
python3 -m unittest discover -s tests -v
sha256sum -c artifacts/threshold_calibration_20260920/SHA256SUMS
```

Provide external repositories and data outside this repository, then export
portable paths instead of editing scripts:

```bash
export FINSCOPE_ROOT="$PWD"
export STOCKBENCH_ROOT=/path/to/stockbench
export FINVAULT_ROOT=/path/to/finvault
export NLPCC_ROOT=/path/to/NLPCC2026-Shared-Task-4/NLPCC_tasks/dataset
export PYTHON=/path/to/python
export PRIVACY_MODEL_BASE_URL=http://127.0.0.1:18002/v1
export PRIVACY_MODEL_NAME=qwen35_4b
export ADAPTIVE_THRESHOLD=0.40
export ADAPTIVE_CALIBRATION="$PWD/artifacts/threshold_calibration_20260920/calibration/adaptive_calibration_llm.json"
```

Deploy Qwen3.5-4B locally and verify `/v1/models`. Deploy one or more
Qwen3.8-27B endpoints and point the StockBench `qwen-proxy*` profiles or bridge
ports `8104/8105/8106` at them. Do not assume the old absolute paths exist.

## Required continuation order

1. Validate the imported artifacts and run the test suite.
2. Run a one-day StockBench FinScope smoke using T=0.40 and confirm exact
   restoration, P-level events, risk lookup, and safe-checkpoint rotation.
3. Audit why the calibration reports have only four NAV observations. If the
   data window is truncated, rerun the four development candidates and K4
   attacks only; never inspect test results when selecting T.
4. Freeze the validated T and run the Qwen3.8-27B six-method main rows:
   Vanilla, Deletion, LLM Rewrite, Fixed Alias, Episode Alias and FinScope
   Adaptive on StockBench, NLPCC and FinVault.
5. Run K4 identity/link attacks on the completed protected trajectories and
   render the three main tables. Keep FinVault native attack success separate
   from ReID/Link privacy attack metrics.
6. Add DeepSeek and GLM task-model rows only after their exact gateway model
   aliases and credentials are verified locally.
7. Run supporting experiments after the main rows: fixed-period replacement,
   safe-checkpoint timing, component ablation, local model selection and fault
   injection. These must not change T.

Useful entry points:

- `benchmarks/run_llm_prior_pipeline.sh`: full calibration plus protected
  follow-up pipeline; use only when intentionally rerunning calibration.
- `benchmarks/resume_llm_threshold_calibration.sh`: regenerate missing attacks
  and selection files from already completed candidate trajectories.
- `benchmarks/run_qwen_external_matrix.sh`: StockBench and FinVault Qwen rows.
- `benchmarks/run_qwen_nlpcc_shards.sh`: NLPCC Qwen rows.
- `benchmarks/run_llm_privacy_attacks.py`: K1-K4 zero-shot ReID/link attacker.
- `benchmarks/render_llm_attack_tables.py`: final attack-table renderer.

## Non-negotiable rules

- Do not train a risk model and do not call request count or trading days the
  leakage value; they are exposure features only.
- Do not merge P-level and T. P-level controls semantic disclosure; T controls
  handle lifetime.
- Do not use simulated tables as measured results. The only committed measured
  calibration data are in the artifact directory above.
- Do not upload model weights, `.env`, API keys, real accounts, real holdings,
  local canonical mappings or unlicensed benchmark datasets.
- Do not execute real trades. Use historical backtests or sandbox execution.
