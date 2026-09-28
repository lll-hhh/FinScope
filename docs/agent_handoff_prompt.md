# New Server Agent Prompt

Use the following prompt after cloning the repository on the new server:

```text
You are taking over the FinScope experiments. First read, in order:

1. docs/experiment_mainline.md
2. docs/migration_handoff_20260928.md
3. artifacts/threshold_calibration_20260920/README.md
4. docs/external_benchmark_integration.md

The current protocol uses Qwen3.8-27B as the task model and Qwen3.5-4B as both
the trusted local privacy Agent model and the training-free privacy attacker.
Risk is obtained from a deterministic empirical K4 attack lookup; do not train
a classifier/regressor and do not restore the obsolete Ridge implementation.
P1-P5 controls semantic disclosure, while T controls handle replacement.

The completed development run selected T=0.40 under a 5% maximum utility-loss
constraint. Verify the committed SHA256 manifest and tests, then investigate
the documented StockBench n=4 reporting limitation before treating this T as a
paper-final value. If the development interval was truncated, rerun only the
development calibration and freeze the corrected artifact without looking at
test results.

After validation, continue with the frozen-T six-method Qwen3.8-27B main rows
on StockBench, NLPCC and FinVault, followed by K4 privacy attacks and table
rendering. Do not begin DeepSeek/GLM or support ablations until those main rows
are complete. Never upload secrets, model weights, external datasets, private
mapping tables or real financial records, and never execute real trades.

Start by reporting: repository commit, test result, GPU/CUDA/vLLM versions,
model paths and endpoint health, benchmark/data availability, artifact checksum
status, and whether StockBench produces the intended development-day count.
Then give the exact first smoke command and proceed unless a required model or
dataset is missing.
```
