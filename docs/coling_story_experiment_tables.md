# FinScope: COLING 论文故事、实验清单与表格草案

更新日期：2026-08-21。`Measured` 表示已有真实实验结果，`TBD` 表示必须补跑，`--` 表示不适用。当前结果来自 NLPCC 2026 Track 1 public A-set 的全年重放，不是官方榜单提交，也不是最终多模型统计结果。

## 1. 论文定位

### 暂定标题

**FinScope: Lifecycle-Bound Semantic Privacy Mediation for Executable Financial Language Agents**

### 一句话主张

外部语言模型既需要足够的金融语义才能决策，又不应看到可重识别的资产与组合身份；FinScope 在本地签发带生命周期的类型化语义句柄，并在输出端确定性恢复、审计和 fail-closed，从而联合优化隐私、金融效用与可执行连续性。

### 论文不应该讲成什么

- 不是“我们提出了一个收益更高的交易策略”。收益只用于证明隐私层没有摧毁下游任务。
- 不是“把股票名替换成随机字符串”。核心是语义披露、scope 生命周期、可验证绑定、确定性恢复和安全执行。
- 不能用 Direct Leak=0 代替隐私证明。最终结论必须依赖强攻击者的 ReID、持仓推断和跨日关联实验。
- 不能把当前 Global Fixed Alias 写成 Episode Alias。当前实现跨日固定，正因如此其 link rate 为 100%。

## 2. 故事主线

### Motivation: 金融 Agent 的三难问题

1. **Vanilla 泄露身份。** 新闻、行情、候选池、持仓和交易 action 中包含真实证券身份，外部模型可直接观察并跨轮聚合。
2. **Deletion 破坏语义与执行。** 删除身份虽然降低直接泄露，但模型无法选择可恢复资产，任务连续性归零。
3. **普通 pseudonym 仍有两个缺口。** 全局固定代号可跨日链接；纯代号缺少金融语义，同时模型输出还必须安全恢复成真实工具参数。

### Method: FinScope 的答案

FinScope 是部署在工具和外部 LLM 之间的本地 Privacy Mediation Agent：

1. security master 提供受信资产事实；
2. P1-P5 planner 选择最小必要语义披露；
3. 本地 binding layer 生成 scope 内稳定、跨日轮换的类型化唯一句柄；
4. 外部 LLM 只看到匿名句柄与经验证的语义描述；
5. 输出在本地确定性恢复，语义 auditor 检测歧义和直接身份复述；
6. 只有通过类型、候选池、数值和交易约束校验的 action 才能执行，否则 fail-closed。

### Evidence: 论文需要建立的四段证据

1. **Privacy:** 对直接泄露、公开新闻/行情重识别、持仓恢复、跨日链接和累计查询攻击均有效。
2. **Utility:** 相比 Deletion、LLM Rewrite 和 opaque alias，FinScope 更好保留各 benchmark 的原生任务分数。
3. **Continuity:** 恢复后的 action、工具参数和环境状态可执行；歧义、旧句柄和损坏 JSON 不会被静默猜测。
4. **Efficiency:** 本地绑定和审计开销小，缓存与门控限制 detector/planner 调用成本。

### 当前结果能讲到哪里

在首个 `NLPCC x Qwen3.8-27B` 全年运行中：

- FinScope 将直接标识泄露从 100% 降到 0%，并将确定性跨日唯一链接从 100% 降到 0%。
- 相对 Vanilla，FinScope 保留 85.2% 累计收益、97.7% Sharpe 和 98.5% Sortino。
- Deletion 的执行成功率为 0%；Global Alias 保留部分效用，但跨日链接仍为 100%。
- FinScope 的执行成功率比 Vanilla 低 2.9 个百分点，输入 token 增加 11.7%，端到端 p95 增加约 1.01 秒。
- FinScope 的决策路径与 Vanilla 明显不同，完整 action agreement 只有 28.0%。因此应写“保留下游金融表现”，不能写“保持相同决策”。

这些结果证明端到端闭环可行，但尚不足以支持“抵抗语义重识别”或“跨模型、跨任务泛化”的最终主张。

## 3. 预期贡献

1. **Lifecycle-bound semantic handles:** 将最小必要金融语义与不可跨 scope 复用的类型化句柄绑定，而非只删除或全局替换身份。
2. **Executable privacy mediation:** 把隐私保护扩展到 LLM 输出、工具参数、本地恢复和真实环境状态转换。
3. **Audited fail-closed restoration:** security-master 验证描述，确定性恢复真实身份，歧义或旧句柄拒绝执行。
4. **Evaluation protocol:** 在连续金融 Agent 中联合评测原生效用、主动隐私攻击、恢复连续性和在线成本。

## 4. 主实验设计

最终核心矩阵为 `3 Benchmarks x 3 Base LMs x 6 Methods`。原计划的五方法不足以排除“仅靠 episode 轮换的 opaque alias 已经足够”这一解释，因此加入 Episode Alias 强基线。

### Benchmarks

- **NLPCC 2026 Track 1:** 主指标 Sharpe；补充 Return、Sortino、MDD、Turnover、执行率。
- **StockBench:** 主指标累计收益；补充 Sortino、MDD、任务完成率和交易成功率。
- **FinVault:** 主指标 benign task success；补充 violation-free execution、attack success、防御率和 over-refusal。

### Base LMs

- Qwen3.8-27B（本地）
- DeepSeek V4 Flash（企业网关实际 alias 待核验）
- GLM-5.1（企业网关实际 alias 待核验）

### Methods

- Vanilla
- Direct Deletion
- LLM Rewrite（同一基座额外做受约束 rewrite，调用成本计入）
- Global Fixed Alias（当前已跑的 `fixed_alias`）
- Episode-scoped Opaque Alias（强基线，跨日轮换但无 P1-P5 语义与恢复 auditor）
- FinScope

### Table 1: 主表，Benchmark x Base Model

主表使用各 benchmark 的原生主指标，不能把不同任务硬平均。单元格为该方法的原生主分数；最后五列报告 FinScope 的隐私、连续性和成本。NLPCC 为 Sharpe，StockBench 为 Return，FinVault 为 benign task success。

| Benchmark | Base LM | Vanilla | Delete | Rewrite | Global Alias | Episode Alias | FinScope | FS Direct Leak ↓ | FS ReID@1 ↓ | FS Link AUC →.5 | FS Task/Exec ↑ | FS Token Δ ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC | Qwen3.8-27B | **2.426** | 0.000 | TBD | 2.264 | TBD | 2.370 | **0.0%** | TBD | TBD | 95.9% | +11.7% |
| NLPCC | DeepSeek V4 Flash | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | GLM-5.1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | Qwen3.8-27B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | DeepSeek V4 Flash | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | GLM-5.1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | Qwen3.8-27B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | DeepSeek V4 Flash | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | GLM-5.1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

主表脚注必须说明：`FS ReID@1` 和 `FS Link AUC` 来自统一强攻击者，而不是字符串扫描；`Task/Exec` 对 NLPCC/StockBench 是执行成功率，对 FinVault 是正常任务完成率。完整的六方法隐私比较放在 Table 3。

## 5. 补充实验表格

### Table 2: NLPCC 原生金融效用（Measured）

| Method | Return ↑ | Sharpe ↑ | Sortino ↑ | MDD ↓ | Ann. Vol. ↓ | Calmar ↑ | Turnover ↓ | Valid ↑ | Executed ↑ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | **39.45%** | **2.426** | 3.582 | 6.88% | 14.67% | **5.986** | 13.038 | 99.2% | 98.8% |
| Deletion | 0.00% | 0.000 | 0.000 | 0.00% | 0.00% | 0.000 | 0.000 | 0.0% | 0.0% |
| LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Global Alias | 25.28% | 2.264 | 3.460 | 4.43% | **10.58%** | 5.950 | 16.623 | 97.5% | 97.5% |
| Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope P3 | 33.60% | 2.370 | **3.529** | 7.64% | 13.04% | 4.588 | 20.448 | 96.3% | 95.9% |

Deletion 的零回撤不是优势，而是从未执行交易。正文不能将其加粗或描述为低风险方法。

### Table 3: 主动隐私攻击

攻击者可观察全部匿名 prompt/output、跨 Agent trace、跨日 trace，以及公开新闻和行情；不可读取本地映射。所有攻击指标报告均值、95% CI、随机基线和候选池规模。

| Method | Direct Leak ↓ | ReID@1 ↓ | ReID@5 ↓ | Pool F1 ↓ | Holding F1 ↓ | Weight MAE ↑ | Action Acc. ↓ | Link AUC →.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 100.0% | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Deletion | 0.0% | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Global Alias | 0.0% | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope P3 | **0.0%** | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

当前另有一个不依赖攻击模型的诊断指标：Global Alias 的跨日唯一字符串链接率为 100%，FinScope 为 0%。它只能作为机制 sanity check，不能替代 Link AUC。

### Table 4: 恢复与流程连续性

| Method | Parse ↑ | Valid/Parsed ↑ | Execute/Valid ↑ | Interrupted ↓ | Exact Restore ↑ | Tool Args ↑ | State Eq. ↑ | Unsafe Repair ↓ | Retry ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 99.2% | 100.0% | 99.6% | 1.2% | -- | -- | 100.0% ref. | -- | TBD |
| Deletion | 100.0% | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% | TBD | TBD | TBD |
| LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Global Alias | 98.8% | 98.8% | 100.0% | 2.5% | TBD | TBD | TBD | TBD | TBD |
| Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope P3 | 97.5% | 98.7% | 99.6% | 4.1% | TBD | TBD | TBD | TBD | TBD |

自然运行中 FinScope 有 6 次 malformed JSON、3 次 `direct_identity_output` 审计拒绝和 1 次卖出空持仓。Exact Restore、State Equivalence 和 Unsafe Repair 必须通过保存本地 ground truth 和故障注入正式评分，不能用 `Valid/Parsed` 代替。

### Table 5: P1-P5 隐私-效用曲线

| Level | Semantic fields | Native utility ↑ | ReID@1 ↓ | Link AUC →.5 | Candidate anonymity ↑ | Exact Restore ↑ | Interrupted ↓ | Tokens ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P1 | 最丰富的受验证语义 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P2 | 较丰富语义 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P3 | 标准语义 | Sharpe 2.370 | TBD | TBD | TBD | TBD | 4.1% | 5,141.5/day |
| P4 | 粗粒度语义 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P5 | 最小语义/执行句柄 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Adaptive | 开发集标定的最小可用级别 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

P1-P5 的具体字段定义应在论文方法表中固定，测试集上不能根据收益反向挑选等级。Adaptive 必须仅在开发集标定。

### Table 6: 恢复鲁棒性与故障注入

| Perturbation | Cases | Exact Restore ↑ | Correct Reject ↑ | Unsafe Repair ↓ | State Eq. ↑ | Retry ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Prefix/suffix/quotes/brackets | TBD | TBD | TBD | TBD | TBD | TBD |
| Descriptor without handle | unit test only | TBD | TBD | TBD | TBD | TBD |
| Swap two same-type handles | TBD | TBD | TBD | TBD | TBD | TBD |
| Truncated/fabricated handle | TBD | TBD | TBD | TBD | TBD | TBD |
| Stale previous-day handle | unit test only | TBD | TBD | TBD | TBD | TBD |
| Coreference points to wrong asset | TBD | TBD | TBD | TBD | TBD | TBD |
| Partial/malformed JSON | natural: 6 rejects | TBD | TBD | TBD | TBD | TBD |
| Out-of-range amount/weight | unit test only | TBD | TBD | TBD | TBD | TBD |
| Tool schema drift | TBD | TBD | TBD | TBD | TBD | TBD |

单元测试只证明预期的软件分支，不应作为论文百分比。正式实验应从真实模型输出生成扰动，并保留可判定的 ground truth。

### Table 7: Privacy Agent 消融

| Variant | Native utility ↑ | ReID@1 ↓ | Link AUC →.5 | Exact Restore ↑ | Unsafe Repair ↓ | Local p95 ↓ | Detector calls ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full FinScope | Sharpe 2.370 | TBD | TBD | TBD | TBD | 12.88 ms | TBD |
| - semantic descriptors, handles only | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| - scope rotation | TBD | TBD | expected high | TBD | TBD | TBD | TBD |
| - security-master validation | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| - restoration auditor | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| - coreference reuse | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Always scan | TBD | TBD | TBD | TBD | TBD | TBD | 100% |
| Gated scan | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| - task cache | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

最关键的两项是 Episode Alias 与 `handles only`。它们用于证明收益来自受验证语义，而隐私与连续性来自生命周期和恢复机制，而不是某一个字符串格式。

### Table 8: 成本与延迟（Measured）

| Method | Input tok/day ↓ | Token Δ | Output tok/day ↓ | Model avg ↓ | Local p95 ↓ | E2E p95 ↓ | Model hours ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 4,602.6 | ref. | 79.5 | 6.914 s | **0.05 ms** | 8.216 s | 0.467 |
| Deletion | **4,447.3** | -3.4% | **69.5** | **6.371 s** | 12.24 ms | **7.751 s** | **0.430** |
| LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Global Alias | 4,606.9 | +0.1% | 72.6 | 6.550 s | 12.70 ms | 8.180 s | 0.442 |
| Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope P3 | 5,141.5 | +11.7% | 95.3 | 8.005 s | 12.88 ms | 9.223 s | 0.540 |

本表只覆盖外部推理时间与当前本地代码时间。最终还要报告 detector/planner/auditor 调用次数、cache hit、probe、峰值显存、API 金额和 GPU 能耗。

### Table 9: 攻击强度与累计泄露

| Setting | Values | ReID@1 ↓ | ReID@5 ↓ | Holding F1 ↓ | Link AUC →.5 | Action Acc. ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Query budget | 1 / 3 / 5 / 10 | TBD | TBD | TBD | TBD | TBD |
| Candidate pool | 20 / 100 / 500 / full | TBD | TBD | TBD | TBD | TBD |
| Observable agents | research / +risk / +trade | TBD | TBD | TBD | TBD | TBD |
| Public side info | none / news / news+prices | TBD | TBD | TBD | TBD | TBD |
| Attack model | Qwen / DeepSeek / GLM | TBD | TBD | TBD | TBD | TBD |

## 6. 实验执行清单

### P0: 论文主张成立前必须完成

1. 实现并运行 Episode Alias 强基线，修正 baseline 命名。
2. 实现同基座 LLM Rewrite，并将额外调用、token、延迟和事实漂移计入。
3. 完成 NLPCC 上三基座 x 六方法主矩阵。
4. 建立本地 attack ground truth，运行 ReID、Pool/Holding recovery、Action inference 和 Link AUC。
5. 运行真实 trace 驱动的恢复故障注入，正式统计 Exact Restore、State Equivalence 和 Unsafe Repair。
6. 为主要 rate 报告 95% CI；金融序列采用 paired moving-block bootstrap，不能把 243 个交易日当独立样本做普通 t-test。

### P1: COLING 完整性所需

7. 接入 StockBench 和 FinVault，完成 3 Bench x 3 LM 的主表。
8. 运行 P1-P5 与 Adaptive，给出隐私-效用 Pareto 曲线。
9. 完成核心消融：handles-only、无轮换、无 security master、无 auditor、always-scan、无 cache。
10. 补充候选池规模、查询预算、公开 side information 和跨 Agent 聚合攻击。
11. 记录 detector/planner/auditor 调用、缓存、probe、GPU 显存/能耗和 API 成本。

### P2: 增强说服力

12. 按牛市、震荡、回撤子区间报告稳定性，不挑选最好窗口。
13. 使用至少两个攻击模型，检查攻击者模型能力敏感性。
14. 对被拒绝的自然输出做错误类型分析，并报告 over-refusal。
15. 发布匿名 trace schema、配置 hash、模型 revision 和可复现实验命令。

## 7. 统计与报告规范

- temperature=0 的本地 greedy run 不靠重复 seed 制造伪方差；金融结果使用时间序列 block bootstrap，云端非确定模型再做 3 次独立运行。
- 所有方法使用相同新闻、行情、候选池、prompt 预算和执行器；LLM Rewrite 的额外调用必须计费。
- 攻击实验按相同候选池和 side information 比较，报告 random/prior baseline。
- Rate 指标给分子/分母和 Wilson 或 bootstrap 95% CI。
- 主表不做跨 benchmark 的无意义平均；如需总览，只报告每个 benchmark 内相对 Vanilla 的 utility retention。
- 预先固定主指标和 P3 默认级别，不能看测试收益后改披露等级。

## 8. 建议的摘要结果句式

最终数字完整后，摘要可按以下结构写：

> Across three financial-agent benchmarks and three base LMs, FinScope reduces active asset re-identification and cross-episode linkage while retaining benchmark-native utility. Unlike deletion, it preserves executable task semantics; unlike globally or episode-scoped opaque aliases, it provides verified minimal financial semantics and audited local restoration. Under restoration faults, FinScope rejects ambiguous outputs rather than silently executing an incorrect asset, with modest local overhead.

当前只能写成 preliminary finding：

> On a full-year NLPCC public A-set replay with Qwen3.8-27B, FinScope eliminates literal identifier exposure and deterministic cross-day handle reuse while retaining 97.7% of Vanilla Sharpe and 85.2% of cumulative return. This result establishes end-to-end feasibility; active semantic re-identification and cross-benchmark generalization remain to be evaluated.

## 9. 当前结论边界

当前已完成 `1/9` 个 Benchmark x Base LM 单元、其中 `4/6` 个方法。可以主张端到端可运行、直接标识不外发、句柄跨日轮换、恢复校验 fail-closed，以及一个全年金融效用结果。不能主张强语义隐私、三模型泛化、三 benchmark 泛化、P1-P5 Pareto 最优或攻击下的完整状态安全，直到对应 `TBD` 被正式实验填满。
