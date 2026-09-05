# FinScope 当前实验表格总骨架

更新日期：2026-09-04。

正式主实验仍是 3 个 Benchmark × 3 个任务模型 × 6 种方法；三个主表额外保留的 `FinScope current（非自适应参考）` 只用于保存已经完成的工程结果，不计入正式方法数，也不能替代尚未运行的 `FinScope Adaptive`。

### 指标来源标记

- **Benchmark/金融标准指标**：Benchmark 原生或金融回测中已有的定义，例如 Return、Sharpe、Sortino 和 MDD；本文直接读取或按原评测流程计算。
- **通用评测指标**：其他领域普遍使用的统计形式，例如 ReID@1、ROC-AUC、MAE、Spearman 相关、token 计数和 p95 延迟；本文只规定金融候选池、攻击信息和采样协议。
- **本文操作性指标**：DP、RC、Exact Action Restore、披露字段数、生命周期、任务中断和状态污染等是为本研究问题定义的确定性测量，不声称是已有标准；每个指标都必须给出分子、分母、代码路径和失败处理。

## 三个核心 Idea

- **Idea 1：本地隐私 Agent。** 使用“作用域句柄 + 任务所需语义 + 本地精确映射”隐藏证券身份、维持多 Agent 引用，并在交易前恢复和校验真实对象。
- **Idea 2：P-level 动态披露。** 本地 Agent 根据角色、任务阶段、数据风险和历史披露状态动态选择 P1-P5，在金融效用与隐私安全之间进行调整。
- **Idea 3：长程风险累计与自适应替换。** 根据匿名轨迹的累计风险和未完成任务依赖选择阈值 T、替换时机和安全检查点，抑制跨日关联且不中断任务。

## 第一组：端到端主实验

这一组回答“FinScope 在不同金融任务上的最终表现如何”，三张表分别对应三个 Benchmark；它们不是消融实验，而是完整方法与基线的主结果。

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

#### 表 1A 指标来源与实现

- **Sharpe、Return、MDD**：Benchmark/金融标准指标；沿用 NLPCC 运行器根据逐日组合价值计算的原定义，不是本文发明。
- **Valid**：任务评测协议指标；本项目在 `benchmarks/run_nlpcc_real.py` 中按“可解析、字段合法、执行器接受”统计合法动作率，具体判定是本项目实现，不应称为普适金融标准。
- **DP（Decision Preservation）**：本文自定义的闭环操作指标，不是通用 Benchmark 指标。当前 `benchmarks/closed_loop_metrics.py` 按 episode 对齐 Vanilla 和保护方法，把动作规范化为“真实资产、方向、工具”签名后比较；两边都有效且签名一致才计为保持。它目前是“精确签名保持”实现，不是分支等价判断，长程任务若出现合法分支必须另行定义可比性，不能直接把 DP=0 解读为方法失败。
- **RC（Reference Continuity）**：本文自定义的多 Agent 指标。`benchmarks/closed_loop_metrics.py` 读取同一 scope 的角色映射，至少两个角色共同看到资产时，检查它们是否指向同一 canonical security。
- **Exact Action Restore**：本文自定义的严格恢复指标。`benchmarks/closed_loop_metrics.py` 用本地 resolver 恢复动作，逐字段比较证券、市场、方向、数量/权重、金额和价格，并要求执行器接受。
- **ReID@1、Link AUC**：通用攻击评测形式 + 本文金融攻击协议，不是 NLPCC 原生指标。`benchmarks/run_nlpcc_privacy_attacks.py` 用公开候选属性匹配计算 Top-1 命中和相邻轨迹 ROC-AUC。
- **Token Δ**：通用系统成本指标，由审计日志中的 token 总数相对 Vanilla 计算。
- **E2E p95**：通用系统延迟指标，由逐请求时间戳取端到端耗时的 95 分位。

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

#### 表 1B 指标来源与实现

- **Return、Sortino、MDD、Sharpe**：StockBench 原生回测/金融指标；由 StockBench 根据逐日净值和收益序列计算，本文只读取 `metrics.json`。
- **DP**：本文自定义指标，当前实现按 episode 用 canonical asset、方向和工具签名比较保护方法与 Vanilla；它不是通用标准，且当前外部 StockBench 日志没有形成可靠可比较分支，故填 `-`，不能把不同合法分支判成零保持。
- **RC**：本文自定义指标，要求同一 scope 的多个角色句柄解析到同一 canonical security；当前没有可比较角色视图，故填 `-`。
- **Exact Action Restore**：本文自定义指标，要求 resolver 恢复完整动作并通过本地执行器；当前 StockBench 汇总未记录完整字段，故填 `-`。
- **ReID@1、Link AUC**：通用攻击指标 + 本文固定公开候选池协议，当前实现由外部汇总器的 catalog oracle 计算，不是 StockBench 原生指标。
- **Token Δ、E2E p95**：通用成本和延迟指标，分别来自审计 token 计数和逐请求端到端时间戳。

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

#### 表 1C 指标来源与实现

- **Benign Success、Attack Success、Violation-free、Over-refusal**：FinVault 场景的固定任务安全评分，底层使用 Benchmark 返回的 reward、动作、拒答、错误和违规状态；这是本项目的评分实现，不是跨任务通用标准。
- **DP**：本文自定义指标，当前实现按 episode 比较 Vanilla 和保护方法的真实对象、方向、工具签名；若正式实验存在多条合法分支，必须先定义分支等价规则，否则应填 `-` 而不是把分支差异记作失败。
- **RC**：本文自定义指标，检查同一 scope 的多角色句柄是否指向同一 canonical security；本轮无角色视图，填 `-`。
- **Exact Action Restore**：本文自定义指标，要求完整动作字段恢复并被本地执行器接受；本轮只有名称/代码级 Exact Restore，故填 `-`。
- **ReID@1、Link AUC**：通用攻击指标 + 本文公开证券候选池协议，使用固定 catalog oracle，不调用任务模型作攻击者。
- **Token Δ、E2E p95**：通用成本和延迟指标，分别由审计日志和请求时间戳计算。

## 第二组：长程风险与攻击证据

这一组先建立问题本身：匿名轨迹变长是否导致效用损失和攻击增强，以及攻击者掌握的公开先验会如何改变风险；它不检验某个组件是否必要。

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

#### 表 2 指标来源与实现

- **Trace Length**：实验控制变量，不是指标；从同一次完整运行截取前 1、5、20、60 日和完整轨迹，不能为每个长度重新挑选日期或随机重跑。
- **Return、Sharpe、MDD、Valid**：沿用 StockBench 的原生回测定义，在截取窗口内重新计算，不是本文发明。
- **Execution Interrupt**：本文定义的长程连续性指标，统计窗口内因句柄替换、恢复失败或安全门控导致任务无法继续的比例；实现时从逐日 `valid`、`executed` 和 `rejection_reason` 日志计数，不能从最终收益倒推。
- **ReID@1、Link AUC**：通用攻击评测指标，使用本文固定的公开候选池和攻击器；NLPCC 现有攻击实现位于 `benchmarks/run_nlpcc_privacy_attacks.py`，长程表只增加轨迹截断，不改变攻击算法。

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

#### 表 3 指标来源与实现

- **Prior Level、Attacker-visible Prior**：实验条件，不是指标；每一级只向攻击器开放明确列出的公开信息，不能读取本地映射、真实持仓或隐藏句柄。
- **Trace Length**：实验条件；攻击器按 1、5、20、60 日和完整轨迹逐步增加观察历史。
- **Candidate Count**：攻击器候选池中的证券数量，是攻击难度记录，不是模型效果分数；必须与随机基线一起报告。
- **Random ReID**：由 `1 / Candidate Count` 得到的随机猜测基线，不是保护方法结果。
- **ReID@1**：攻击器根据匿名对象与候选证券公开属性的匹配分数排序，第一名命中真实证券才记 1，最后按样本平均；属于通用 Top-1 攻击指标，金融候选池和匹配规则是本文协议，NLPCC 实现位于 `benchmarks/run_nlpcc_privacy_attacks.py`，外部结果汇总位于 `benchmarks/summarize_external_matrix.py`。
- **Link AUC**：把相邻轨迹的同证券配对作为正例、不同证券配对作为负例，用公开特征相似度排序并计算 ROC-AUC；0.5 是随机关联，属于通用分类指标，具体配对和 `roc_auc` 实现位于 `benchmarks/run_nlpcc_privacy_attacks.py`。
- **Attack Queries**：攻击器实际读取或比较的轨迹/候选次数，由攻击日志计数；用于描述攻击预算，不是隐私强度本身。

## 第三组：自适应机制验证

这一组验证两个自适应决策：P-level 选择披露多少，以及风险达到什么程度、在什么时机触发替换。表 4 是披露策略对比，表 5 是替换周期对比，表 6 是替换时机对比，表 7 是风险估计和阈值校准对比；其中表 6 不是消融，表 7 也不是单纯删组件，而是比较替换决策规则。

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

#### 表 4 指标来源与实现

- **Disclosure Policy**：实验条件；固定行每个请求使用指定 P-level，动态行由本地 Agent 根据角色、阶段、风险和累计暴露选择。当前仓库已有固定 P1-P5 字段映射和请求级升级规则，但还没有完成经过开发集校准的动态 P-level runner，因此动态行目前必须填 `-`。
- **Mean P-level**：本文定义的描述性统计，记录所有请求实际等级的平均值；它不是隐私泄露概率。
- **P1/P2/P3/P4/P5 Distribution**：按审计日志统计各等级请求数占比，用来证明动态策略是否真的改变等级。
- **Disclosed Fields / Asset**：本文定义的披露量代理，统计每个资产实际外发的非身份语义字段数量；字段集合由 `finscope/privacy_agent.py` 中 P1-P5 的允许字段决定。它是解释 P-level 的辅助统计，不是已被领域统一采用的隐私分数。
- **Return、Sharpe、MDD、Valid**：沿用 NLPCC 的原生金融评测实现。
- **ReID@1、Link AUC**：通用攻击指标加本文公开侧信息攻击协议，计算方式与表 3 相同。
- **Token Δ、E2E p95**：通用成本和延迟指标，分别由审计 token 计数和端到端时间戳计算。

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

#### 表 5 指标来源与实现

- **Rotation Policy**：实验条件；固定策略按预设生命周期更新，Adaptive T 根据累计风险和任务状态更新。当前代码还没有完成表 5 的风险驱动轮换 runner，因此正式结果必须填 `-`。
- **Mean Lifetime (days)**：本文定义的生命周期统计，从句柄创建时间到更新/失效时间按交易日计数并取平均。
- **Rotation Count**：从运行日志统计句柄更新事件的总次数；它是行为统计，不是隐私泄露量。
- **Return、Sharpe、MDD、Valid**：沿用 StockBench 的原生回测指标。
- **ReID@1、Link AUC**：通用攻击指标，在相同候选池和公开先验下计算，用来比较不同生命周期的实际攻击后果。
- **Reference Failure**：本文定义的连续性指标，统计旧句柄无法解析、解析到错误证券或跨 scope 被错误复用的比例。
- **Token Δ、E2E p95**：通用系统成本和端到端延迟指标。

### 表 6：替换时机与任务连续性

**说明：** 本表在相同累计风险下只改变句柄替换发生的位置，作用是证明任务依赖状态和安全检查点能够降低替换造成的引用断裂与执行中断，服务 Idea 1 和 Idea 3。

| Rotation Timing | Risk at Rotation | Pending Dependency at Rotation | Reference Continuity ↑ | Task Interrupt ↓ | Invalid Action ↓ | Return ↑ | ReID@1 ↓ | Link AUC →.5 | Mean Delay to Rotation ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No rotation | - | - | - | - | - | - | - | - | - |
| Immediate during analysis | - | - | - | - | - | - | - | - | - |
| After tool call | - | - | - | - | - | - | - | - | - |
| After trading stage | - | - | - | - | - | - | - | - | - |
| FinScope safe checkpoint | - | - | - | - | - | - | - | - | - |

#### 表 6 指标来源与实现

- **Rotation Timing**：实验条件；保持风险阈值和替换策略不变，只规定替换发生在分析中、工具调用后、交易阶段后或安全检查点。
- **Risk at Rotation**：依赖本文风险估计器的状态输出，记录触发替换时的预测风险值；在没有实现风险估计器前必须填 `-`，不能用请求数代替。
- **Pending Dependency at Rotation**：读取本地任务状态，标记当前是否仍有研究结论、风控判断或待执行动作依赖旧句柄；这是状态标签，不是模型 Judge 分数。
- **Reference Continuity**：本文定义的 RC，按同一 scope 内角色映射是否仍指向同一 canonical security 计算。
- **Task Interrupt**：从任务日志统计因替换、恢复失败或安全检查导致流程中断的比例。
- **Invalid Action**：由本地动作 schema 和市场约束验证器判定恢复动作是否非法，统计非法动作占比。
- **Return、ReID@1、Link AUC**：分别沿用 Benchmark 回测和本文固定攻击协议。
- **Mean Delay to Rotation**：记录风险达到触发条件到实际在安全节点完成替换之间的时间差，属于本文过程统计。

### 表 7：风险估计器与阈值选择

**说明：** 本表用开发集选择并冻结请求数、交易日数、完整暴露状态估计器及事后最优上限的阈值，作用是证明 T 来自可复现的数据校准而不是人工拍定，服务 Idea 3。

| Risk Method | Input State | Dev Threshold T | Risk MAE ↓ | Risk Rank Corr. ↑ | Test ReID@1 ↓ | Test Link AUC →.5 | Utility Loss ↓ | Mean Rotation Period | Gap to Oracle ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Request-count threshold | 请求累计次数 | - | - | - | - | - | - | - | - |
| Trading-day threshold | 句柄持续交易日 | - | - | - | - | - | - | - | - |
| Exposure-state estimator | 次数、时长、角色、行情与行为关联 | - | - | - | - | - | - | - | - |
| Development-set oracle | 事后真实攻击结果 | - | 0 | 1 | - | - | - | - | 0 |

#### 表 7 指标来源与实现

- **Risk Method、Input State**：实验条件；前两行是简单基线，第三行使用本地状态特征，最后一行只作为开发集可计算上限，不能在线部署。当前仓库只有 `finscope/policy.py` 的请求计数式升级规则，没有完成“离线攻击结果 -> 风险估计器 -> 冻结 T”的完整实现，因此表 7 不是现有结果表。
- **Dev Threshold T**：在开发集扫描候选阈值，先筛掉超过允许效用损失的策略，再选择攻击风险最低的阈值；选定后冻结到测试集。
- **Risk MAE**：通用回归误差指标，比较估计风险与离线攻击得到的实际风险，越低越好；没有风险估计器时填 `-`。
- **Risk Rank Corr.**：通用排序一致性指标，比较估计风险排序和真实攻击风险排序，通常使用 Spearman 相关；不是 FinScope 特有指标。
- **Test ReID@1、Test Link AUC**：在冻结 T 后的测试集攻击结果，不允许用测试结果回调阈值。
- **Utility Loss**：相对不保护 Vanilla 的 Return、Sharpe 或 Valid 下降幅度，是由已有 Benchmark 指标派生的比较量，不是新的金融指标。
- **Mean Rotation Period**：测试期间实际句柄生命周期的平均值，由轮换事件时间戳计算。
- **Gap to Oracle**：实际策略与开发集事后最优策略在隐私或效用目标上的差距，是本文定义的参考量，不能宣称为通用标准。

## 第四组：可行性、因果消融与执行安全

这一组回答“本地隐私 Agent 是否可行、FinScope 的组件是否必要、恢复错误是否会被交易前安全边界拦截”。表 8 是模型选择，表 9 才是严格意义上的组件消融，表 10 是故障注入实验。

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

#### 表 8 指标来源与实现

- **Local Model、Size、Status**：模型元数据和运行可用性，不是效果指标；参数量来自模型配置，Status 记录是否有权重、是否完成严格开发集测试以及是否被选中。
- **Strict Planner Valid**：本文定义的本地 Agent 协议指标。在禁止整链 deterministic fallback 的条件下，规划器输出必须是完整 JSON、等级只能是 P1-P5、字段必须属于该等级允许集合并通过本地校验，成功次数除以规划调用次数；统计实现位于 `benchmarks/run_nlpcc_local_model_ablation.py`。
- **Recognizer Fail、Auditor Fail**：本文定义的角色级失败率，分别统计识别器无法返回合法实体结果、恢复审计器无法返回合法审计结果的调用比例。
- **Whole-chain Fallback**：由运行计数器统计整条本地 Agent 链路退回确定性规则的次数；它与允许的字段级安全修正分开，不把 fallback 伪装成模型成功。
- **Planner Repair**：统计本地规划器输出经过字段去重、范围规范化等安全修正的调用比例；修正后仍不合法的样本不计为成功。
- **Local Tokens、Local p95**：通用模型成本和延迟指标，只统计本地 Agent，不包含 Qwen3.8-27B 任务模型耗时。

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

#### 表 9 指标来源与实现

- **Variant、Removed Component**：实验条件；完整 FinScope 作为对照，每个变体只关闭一个组件，其余模型、数据、提示和随机设置保持不变。当前尚无完成表 9 全部变体的统一 runner，故所有正式数字先填 `-`。
- **Return、Sharpe、Valid**：沿用 StockBench 原生回测和动作合法率实现，用于检查删除组件是否影响金融任务。
- **ReID@1、Link AUC**：通用攻击指标，使用与主实验相同的候选池、公开先验和攻击器，避免因攻击配置变化造成假差异。
- **RC**：本文自定义的作用域引用连续性指标，检查跨角色句柄是否解析到同一 canonical security。
- **Rotation Count**：从事件日志统计句柄更新次数；它只说明组件改变了多少次轮换，不直接等于泄露量。
- **Task Interrupt**：从任务事件日志统计被替换或恢复过程打断的任务比例。
- **Token Δ、E2E p95**：通用成本和延迟指标；完整方法与消融使用同一基准计算相对变化。

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

#### 表 10 指标来源与实现

- **Injected Fault、Cases**：实验条件和样本数；故障从真实已接受的模型输出复制后注入，不使用纯 toy 输入，Cases 是该类故障的分母。
- **Detection Rate**：本地 resolver、scope validator、动作 validator 或 business validator 报告对应错误的比例；NLPCC 现有故障注入计数可参考 `benchmarks/run_nlpcc_fault_injection.py`，但它不能直接替代表 10 所需的 FinVault 实验。
- **Correct Reject**：输入确实有问题且系统拒绝执行、错误码正确、真实 portfolio state 未变化的比例；这是本文的安全门控操作指标。
- **Wrong Execution**：危险或错误动作通过验证器并进入执行器的比例，越低越好。
- **Fail-closed**：无法确认身份或动作时系统停止而不是猜测继续的比例，属于本文安全协议指标。
- **State Pollution**：故障处理后本地证券映射、持仓或任务状态被错误改变的比例，属于本文定义的状态完整性指标。
- **Reason-code Coverage**：每个拒绝样本是否落入可审计错误类别的比例，属于实现审计指标。
- **Extra p95**：故障检测和拒绝路径相对正常路径增加的端到端 95 分位延迟，使用通用 p95 统计方法。

## 指标口径总览

每张表下面已经给出该表所有列的来源和实现；本节只保留一个总规则：Benchmark 原生指标沿用原评测实现，ReID@1/Link AUC 使用固定公开攻击协议，DP/RC/Exact Action Restore、披露量、生命周期、风险估计和故障门控属于本文定义的可复现操作指标，不能冒充已有通用标准。

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

- `DP` 为本文自定义的 Decision Preservation；当前代码是精确动作签名保持，不是已有标准，也不能把长程任务中不同的合法分支全部判为失败。没有分支等价标注时保持 `-`。
- `Exact Restore` 不能替代 `Exact Action Restore`；只有恢复后的证券、市场、方向、数量或权重通过本地交易约束时才填后者。
- 当前公开的 P1-P5 攻击数字来自旧版实现，不能填入表 4；表 2-7、表 9-10 在新版 Adaptive 方法正式运行前保持 `-`。
- 正文建议放表 1A-1C、表 3、表 4、表 5 和表 9，其他表放附录。
