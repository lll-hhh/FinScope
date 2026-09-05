# FinScope 当前实验表格总骨架

更新日期：2026-09-04。

正式主实验仍是 3 个 Benchmark × 3 个任务模型 × 6 种方法；三个主表额外保留的 `FinScope current（非自适应参考）` 只用于保存已经完成的工程结果，不计入正式方法数，也不能替代尚未运行的 `FinScope Adaptive`。

## 三个核心 Idea

- **Idea 1：本地隐私 Agent。** 使用“作用域句柄 + 任务所需语义 + 本地精确映射”隐藏证券身份、维持多 Agent 引用，并在交易前恢复和校验真实对象。
- **Idea 2：P-level 动态披露。** 本地 Agent 根据角色、任务阶段、数据风险和历史披露状态动态选择 P1-P5，在金融效用与隐私安全之间进行调整。
- **Idea 3：长程风险累计与自适应替换。** 根据匿名轨迹的累计风险和未完成任务依赖选择阈值 T、替换时机和安全检查点，抑制跨日关联且不中断任务。

## 第一组：跨 Benchmark 主结果

### 表 1A：NLPCC 主表

**说明：** 本表在 NLPCC 上比较 3 个任务模型和 6 种方法的金融决策、闭环恢复、隐私攻击与成本，作用是给出端到端总体结论，联合服务 Idea 1、Idea 2 和 Idea 3。

| Base Model | Method | Sharpe ↑ | Return ↑ | MDD ↓ | Valid ↑ | DP ↑ | RC ↑ | Exact Action Restore ↑ | ReID@1 ↓ | Link AUC →.5 | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.8-27B | Vanilla | 2.807 | 58.16% | 8.61% | 99.59% | 99.59% | 100% | - | - | - | 0.00% | 21.303s |
| Qwen3.8-27B | Deletion | 0.000 | 0.00% | 0.00% | 0.00% | - | - | - | - | - | -1.76% | 21.026s |
| Qwen3.8-27B | LLM Rewrite | 2.373 | 40.91% | 10.91% | 99.18% | - | 100% | 99.18% | - | - | +11.60% | 39.480s |
| Qwen3.8-27B | Fixed Alias | 2.525 | 33.14% | 6.46% | 98.77% | - | 100% | 98.77% | - | - | +2.49% | 21.013s |
| Qwen3.8-27B | Episode Alias | 3.064 | 61.13% | 8.61% | 99.18% | - | 100% | 99.18% | - | - | +4.22% | 20.623s |
| Qwen3.8-27B | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| Qwen3.8-27B | FinScope current（非自适应参考） | 1.912 | 16.03% | 5.57% | 100.00% | - | 100% | 100.00% | - | - | -32.30% | 76.275s |
| DeepSeek V4 Flash | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |

### 表 1B：StockBench 主表

**说明：** 本表在 StockBench 上比较长程交易收益、闭环恢复、轨迹攻击与运行成本，作用是验证方法在连续市场任务中的总体表现，联合服务 Idea 1、Idea 2 和 Idea 3。

| Base Model | Method | Return ↑ | Sortino ↑ | MDD ↓ | Sharpe ↑ | DP ↑ | RC ↑ | Exact Action Restore ↑ | ReID@1 ↓ | Link AUC →.5 | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.8-27B | Vanilla | 4.24% | 2.253 | 2.43% | 1.679 | - | - | - | 100.00% | 1.000 | 0.00% | 253.267s |
| Qwen3.8-27B | Deletion | 0.00% | 0.000 | 0.00% | 0.000 | 0.00% | - | - | 5.00% | 0.500 | -9.03% | 136.463s |
| Qwen3.8-27B | LLM Rewrite | 0.00% | 0.000 | 0.00% | 0.000 | 0.00% | - | - | 100.00% | 1.000 | -7.50% | 95.530s |
| Qwen3.8-27B | Fixed Alias | -1.75% | -0.111 | 12.17% | -0.096 | 0.00% | 100% | - | 5.00% | 1.000 | +2.51% | 157.654s |
| Qwen3.8-27B | Episode Alias | -1.49% | -0.066 | 11.87% | -0.056 | 0.00% | 100% | - | 5.00% | 0.500 | +2.58% | 155.532s |
| Qwen3.8-27B | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| Qwen3.8-27B | FinScope current（非自适应参考） | 0.00% | 0.000 | 0.00% | 0.000 | 0.00% | 100% | - | 30.00% | 0.926 | +10.75% | 164.488s |
| DeepSeek V4 Flash | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |

### 表 1C：FinVault 主表

**说明：** 本表在 FinVault 上比较正常任务完成、攻击诱导、违规执行和隐私恢复，作用是检验方法是否同时保持可用性与执行安全，联合服务 Idea 1、Idea 2 和 Idea 3。

| Base Model | Method | Benign Success ↑ | Attack Success ↓ | Violation-free ↑ | Over-refusal ↓ | DP ↑ | RC ↑ | Exact Action Restore ↑ | ReID@1 ↓ | Link AUC →.5 | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.8-27B | Vanilla | 39.25% | 17.76% | 74.77% | 36.45% | - | - | - | 100.00% | 1.000 | 0.00% | 33.478s |
| Qwen3.8-27B | Deletion | 35.51% | 14.02% | 78.50% | 39.25% | 83.96% | - | - | 1.59% | 0.859 | -5.92% | 44.247s |
| Qwen3.8-27B | LLM Rewrite | 29.91% | 0.93% | 89.72% | 61.68% | 27.85% | - | - | 1.88% | 0.859 | +8.36% | 79.612s |
| Qwen3.8-27B | Fixed Alias | 38.32% | 17.76% | 74.77% | 36.45% | 89.71% | - | - | 0.14% | 1.000 | +0.88% | 45.138s |
| Qwen3.8-27B | Episode Alias | 37.38% | 15.89% | 76.64% | 38.32% | 89.04% | - | - | 0.14% | 0.500 | +0.04% | 42.748s |
| Qwen3.8-27B | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| Qwen3.8-27B | FinScope current（非自适应参考） | 26.17% | 9.35% | 82.24% | 53.27% | 84.43% | - | - | 1.59% | 0.859 | -27.30% | 47.518s |
| DeepSeek V4 Flash | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| DeepSeek V4 Flash | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Vanilla | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Deletion | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | LLM Rewrite | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Fixed Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | Episode Alias | - | - | - | - | - | - | - | - | - | - | - |
| GLM-5.1 | FinScope Adaptive | - | - | - | - | - | - | - | - | - | - | - |

## 第二组：长程隐私风险与攻击依据

### 表 2：轨迹增长下的效用与隐私风险

**说明：** 本表在 StockBench/Qwen3.8-27B 上只改变匿名轨迹长度并比较 Fixed Alias、Episode Alias 和 FinScope Adaptive，作用是证明效用损失与身份攻击是否随长程状态累积，服务 Idea 3。

| Method | Trace Length | Return ↑ | Sharpe ↑ | MDD ↓ | Valid ↑ | Execution Interrupt ↓ | ReID@1 ↓ | Link AUC →.5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed Alias | 1 日 | - | - | - | - | - | - | - |
| Fixed Alias | 5 日 | - | - | - | - | - | - | - |
| Fixed Alias | 20 日 | - | - | - | - | - | - | - |
| Fixed Alias | 60 日 | - | - | - | - | - | - | - |
| Fixed Alias | 完整轨迹 | - | - | - | - | - | - | - |
| Episode Alias | 1 日 | - | - | - | - | - | - | - |
| Episode Alias | 5 日 | - | - | - | - | - | - | - |
| Episode Alias | 20 日 | - | - | - | - | - | - | - |
| Episode Alias | 60 日 | - | - | - | - | - | - | - |
| Episode Alias | 完整轨迹 | - | - | - | - | - | - | - |
| FinScope Adaptive | 1 日 | - | - | - | - | - | - | - |
| FinScope Adaptive | 5 日 | - | - | - | - | - | - | - |
| FinScope Adaptive | 20 日 | - | - | - | - | - | - | - |
| FinScope Adaptive | 60 日 | - | - | - | - | - | - | - |
| FinScope Adaptive | 完整轨迹 | - | - | - | - | - | - | - |

### 表 3：公开先验攻击

**说明：** 本表在 StockBench/Qwen3.8-27B 的全市场候选集中逐级加入证券主表、静态属性、历史行情和跨轮行为先验，作用是得到可复现的实际攻击强度并为在线风险估计提供监督目标，服务 Idea 3。

| Prior Level | Attacker-visible Prior | Trace Length | Candidate Count | Random ReID | ReID@1 ↓ | Link AUC →.5 | Attack Queries |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| K1 | 证券主表 | 1 日 | - | - | - | - | - |
| K1 | 证券主表 | 5 日 | - | - | - | - | - |
| K1 | 证券主表 | 20 日 | - | - | - | - | - |
| K1 | 证券主表 | 60 日 | - | - | - | - | - |
| K1 | 证券主表 | 完整轨迹 | - | - | - | - | - |
| K2 | 主表 + 静态属性 | 1 日 | - | - | - | - | - |
| K2 | 主表 + 静态属性 | 5 日 | - | - | - | - | - |
| K2 | 主表 + 静态属性 | 20 日 | - | - | - | - | - |
| K2 | 主表 + 静态属性 | 60 日 | - | - | - | - | - |
| K2 | 主表 + 静态属性 | 完整轨迹 | - | - | - | - | - |
| K3 | 主表 + 静态属性 + 历史行情 | 1 日 | - | - | - | - | - |
| K3 | 主表 + 静态属性 + 历史行情 | 5 日 | - | - | - | - | - |
| K3 | 主表 + 静态属性 + 历史行情 | 20 日 | - | - | - | - | - |
| K3 | 主表 + 静态属性 + 历史行情 | 60 日 | - | - | - | - | - |
| K3 | 主表 + 静态属性 + 历史行情 | 完整轨迹 | - | - | - | - | - |
| K4 | 主表 + 静态属性 + 历史行情 + 跨轮行为 | 1 日 | - | - | - | - | - |
| K4 | 主表 + 静态属性 + 历史行情 + 跨轮行为 | 5 日 | - | - | - | - | - |
| K4 | 主表 + 静态属性 + 历史行情 + 跨轮行为 | 20 日 | - | - | - | - | - |
| K4 | 主表 + 静态属性 + 历史行情 + 跨轮行为 | 60 日 | - | - | - | - | - |
| K4 | 主表 + 静态属性 + 历史行情 + 跨轮行为 | 完整轨迹 | - | - | - | - | - |

## 第三组：P-level 与 T 自适应机制

### 表 4：动态 P-level 与固定披露

**说明：** 本表在 NLPCC/Qwen3.8-27B 上比较固定 P1-P5 与动态 P-level 并同时报告效用、隐私和成本，作用是验证场景感知披露是否优于单一固定保护等级，服务 Idea 2。

| Disclosure Policy | Mean P-level | P1/P2/P3/P4/P5 Distribution | Disclosed Fields / Asset ↓ | Return ↑ | Sharpe ↑ | MDD ↓ | Valid ↑ | ReID@1 ↓ | Link AUC →.5 | Token Δ ↓ | E2E p95 ↓ |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed P1 | 1.00 | 100/0/0/0/0 | - | - | - | - | - | - | - | - | - |
| Fixed P2 | 2.00 | 0/100/0/0/0 | - | - | - | - | - | - | - | - | - |
| Fixed P3 | 3.00 | 0/0/100/0/0 | - | - | - | - | - | - | - | - | - |
| Fixed P4 | 4.00 | 0/0/0/100/0 | - | - | - | - | - | - | - | - | - |
| Fixed P5 | 5.00 | 0/0/0/0/100 | - | - | - | - | - | - | - | - | - |
| Dynamic P-level | - | - | - | - | - | - | - | - | - | - | - |

### 表 5：自适应 T 与固定替换周期

**说明：** 本表在 StockBench/Qwen3.8-27B 上比较不替换、固定周期、按任务替换和风险驱动自适应替换，作用是证明累计风险阈值 T 是否能取得固定生命周期无法达到的效用—隐私折中，服务 Idea 3。

| Rotation Policy | Mean Lifetime (days) ↓ | Rotation Count | Return ↑ | Sharpe ↑ | MDD ↓ | Valid ↑ | ReID@1 ↓ | Link AUC →.5 | Reference Failure ↓ | Token Δ ↓ | E2E p95 ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Never rotate | - | - | - | - | - | - | - | - | - | - | - |
| Every 20 days | - | - | - | - | - | - | - | - | - | - | - |
| Every 5 days | - | - | - | - | - | - | - | - | - | - | - |
| Every day | - | - | - | - | - | - | - | - | - | - | - |
| Every task | - | - | - | - | - | - | - | - | - | - | - |
| FinScope adaptive T | - | - | - | - | - | - | - | - | - | - | - |

### 表 6：替换时机与任务连续性

**说明：** 本表在相同累计风险下只改变句柄替换发生的位置，作用是证明任务依赖状态和安全检查点能够降低替换造成的引用断裂与执行中断，服务 Idea 1 和 Idea 3。

| Rotation Timing | Risk at Rotation | Pending Dependency at Rotation | Reference Continuity ↑ | Task Interrupt ↓ | Invalid Action ↓ | Return ↑ | ReID@1 ↓ | Link AUC →.5 | Mean Delay to Rotation ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No rotation | - | - | - | - | - | - | - | - | - |
| Immediate during analysis | - | - | - | - | - | - | - | - | - |
| After tool call | - | - | - | - | - | - | - | - | - |
| After trading stage | - | - | - | - | - | - | - | - | - |
| FinScope safe checkpoint | - | - | - | - | - | - | - | - | - |

### 表 7：风险估计器与阈值选择

**说明：** 本表用开发集选择并冻结请求数、交易日数、完整暴露状态估计器及事后最优上限的阈值，作用是证明 T 来自可复现的数据校准而不是人工拍定，服务 Idea 3。

| Risk Method | Input State | Dev Threshold T | Risk MAE ↓ | Risk Rank Corr. ↑ | Test ReID@1 ↓ | Test Link AUC →.5 | Utility Loss ↓ | Mean Rotation Period | Gap to Oracle ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Request-count threshold | 请求累计次数 | - | - | - | - | - | - | - | - |
| Trading-day threshold | 句柄持续交易日 | - | - | - | - | - | - | - | - |
| Exposure-state estimator | 次数、时长、角色、行情与行为关联 | - | - | - | - | - | - | - | - |
| Development-set oracle | 事后真实攻击结果 | - | 0 | 1 | - | - | - | - | 0 |

## 第四组：本地 Agent 与执行安全支撑

### 表 8：本地隐私 Agent 模型选择

**说明：** 本表在固定 NLPCC 20 日开发集上比较 10 个不超过 4B 的本地模型，作用是证明隐私 Agent 可以由小模型可靠承担并锁定后续正式实验模型，服务 Idea 1。

| Local Model | Size | Strict Planner Valid ↑ | Recognizer Fail ↓ | Auditor Fail ↓ | Whole-chain Fallback ↓ | Planner Repair ↓ | Local Tokens ↓ | Local p95 ↓ | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3.5-0.8B | 0.8B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Qwen3.5-2B | 2B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Qwen3.5-4B | 4B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Qwen3-0.6B | 0.6B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Qwen3-1.7B | 1.7B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Llama-3.2-1B-Instruct | 1B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Llama-3.2-3B-Instruct | 3B | 100% | 0 | 0 | 0 | - | - | 48.70s | 已选定 |
| Gemma-3-1B-it | 1B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Gemma-3-4B-it | 4B | - | - | - | - | - | - | - | 未形成合格完整结果 |
| Gemma-4-4B-it | 4B | - | - | - | - | - | - | - | 当前配置不可用 |

### 表 9：关键组件消融

**说明：** 本表在 StockBench/Qwen3.8-27B 上每次只移除一个 FinScope 组件，作用是区分动态披露、风险累计、任务依赖和安全恢复各自带来的效果，联合服务 Idea 1、Idea 2 和 Idea 3。

| Variant | Removed Component | Return ↑ | Sharpe ↑ | Valid ↑ | ReID@1 ↓ | Link AUC →.5 | RC ↑ | Rotation Count | Task Interrupt ↓ | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full FinScope Adaptive | None | - | - | - | - | - | - | - | - | - | - |
| No dynamic P-level | 场景感知披露选择 | - | - | - | - | - | - | - | - | - | - |
| No exposure memory | 累计暴露状态 | - | - | - | - | - | - | - | - | - | - |
| No risk estimator | 攻击风险反向估计 | - | - | - | - | - | - | - | - | - | - |
| No task dependency | 未完成任务依赖状态 | - | - | - | - | - | - | - | - | - | - |
| No safe checkpoint | 延迟到安全节点替换 | - | - | - | - | - | - | - | - | - | - |
| No mapping cache | 任务内映射缓存 | - | - | - | - | - | - | - | - | - | - |
| No master validation | 证券主表与类型校验 | - | - | - | - | - | - | - | - | - | - |

### 表 10：故障安全与错误恢复

**说明：** 本表在 FinVault/Qwen3.8-27B 的真实已接受轨迹上注入句柄和交易参数故障，作用是验证恢复异常会在本地交易提交前被明确拒绝且不会污染金融状态，服务 Idea 1。

| Injected Fault | Cases | Detection Rate ↑ | Correct Reject ↑ | Wrong Execution ↓ | Fail-closed ↑ | State Pollution ↓ | Reason-code Coverage ↑ | Extra p95 ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unknown/fabricated handle | - | - | - | - | - | - | - | - |
| Expired previous-scope handle | - | - | - | - | - | - | - | - |
| Mapping collision | - | - | - | - | - | - | - | - |
| Same-type handle swap | - | - | - | - | - | - | - | - |
| Missing/failed restoration | - | - | - | - | - | - | - | - |
| Illegal market/direction/quantity/weight/price | - | - | - | - | - | - | - | - |

## 表格与论文主张的对应关系

| Table | Primary Evidence | Served Idea |
| --- | --- | --- |
| 1A-1C | 三个 Benchmark 的总体效用、隐私、安全和成本 | Idea 1 + Idea 2 + Idea 3 |
| 2 | 长程轨迹是否造成效用衰减和攻击增强 | Idea 3 |
| 3 | 累计风险信号来自什么公开攻击证据 | Idea 3 |
| 4 | 动态 P-level 是否优于固定披露 | Idea 2 |
| 5 | 自适应 T 是否优于固定替换周期 | Idea 3 |
| 6 | 为什么替换必须考虑任务依赖和安全检查点 | Idea 1 + Idea 3 |
| 7 | 风险估计器和阈值 T 如何数据化确定 | Idea 3 |
| 8 | 为什么本地隐私 Agent 可以使用不超过 4B 的模型 | Idea 1 |
| 9 | 每个方法组件是否必要 | Idea 1 + Idea 2 + Idea 3 |
| 10 | 恢复错误为何属于交易执行安全问题 | Idea 1 |

## 使用边界

- `DP` 为 Decision Preservation，`RC` 为 Reference Continuity；分支不同的长程轨迹不能用逐动作完全相同冒充决策保持，未形成可靠值时保持 `-`。
- `Exact Restore` 不能替代 `Exact Action Restore`；只有恢复后的证券、市场、方向、数量或权重通过本地交易约束时才填后者。
- 当前公开的 P1-P5 攻击数字来自旧版实现，不能填入表 4；表 2-7、表 9-10 在新版 Adaptive 方法正式运行前保持 `-`。
- 正文建议放表 1A-1C、表 3、表 4、表 5 和表 9，其他表放附录。
