# FinScope: COLING 论文故事、实验清单与表格草案

更新日期：2026-08-23。`Measured` 表示已有真实实验结果，`TBD` 表示必须补跑，`--` 表示不适用。当前结果来自 NLPCC 2026 Track 1 public A-set 的全年重放，不是官方榜单提交，也不是最终多模型统计结果。

### 重跑状态（Qwen 小模型本地 Agent）

此前表中的全年 Qwen3.8-27B 数字来自 deterministic local-agent 版本，只保留为 preliminary engineering reference；不能当作本地小模型最终结果。新协议固定 Qwen3.8-27B 为任务模型，另用不超过 4B 的本地小模型承担识别、规划和审计，并在严格模式下禁止整套 fallback。当前 Qwen3.5-2B 已通过双资产三角色 toy smoke 和 11 资产单交易日 NLPCC pipeline smoke；这不是全年统计，主表的全年单元仍保持 `TBD`。2026-08-23 的 StockBench/FinVault 重跑在 Qwen 8104 服务退出后出现 502，已停止并隔离，所有中间产物均不进入表格；正式重跑必须从新的 run root 开始。正式候选固定为 `benchmarks/local_privacy_models.json` 中的 10 个模型。

## 1. 论文定位

### 暂定标题

**FinScope: A Local Agent for Semantic Assurance under Privacy Constraints in Financial Multi-Agent Systems**

### 一句话主张

外部语言模型既需要足够的金融语义才能决策，又不应看到不必要的真实资产与组合身份；FinScope 作为金融多智能体系统中新加入的本地 Agent，维护受验证的金融语义与唯一句柄，在输出端确定性恢复、审计并 fail-closed，使经过保护的信息仍能可靠地支持工具和交易执行。

完整的问题定义、故事边界和相关工作新颖性审计见 [`coling_problem_story_related_work.md`](coling_problem_story_related_work.md)。

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

FinScope 是金融多智能体系统中新增的本地语义保障 Agent：

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
- 相对 Vanilla，FinScope 保留 87.0% 累计收益；Sharpe 为 2.976（Vanilla 2.426），MDD 为 3.34%（Vanilla 6.88%）。
- Deletion 的执行成功率为 0%；Global Alias 保留部分效用，但跨日链接仍为 100%。
- 公开行情 oracle 下，FinScope P3 将 ReID@1 从其他方法的 100% 降到 53.20%，Link AUC 从 1.000 降到 0.789；这说明风险下降但远未完全匿名。P5 达到随机基线，但金融效用低于 P3。
- FinScope 的执行成功率为 99.2%，输入 token 比 Vanilla 少 50.9%，端到端 p95 从 8.216 秒降到 7.031 秒。

这些结果证明端到端闭环可行，但尚不足以支持“抵抗语义重识别”或“跨模型、跨任务泛化”的最终主张。

## 3. 预期贡献

1. **Recoverable financial bindings:** 接收 A1/共享保护模块产生的 P1-P5 描述，将其绑定到 canonical entity、scope 和允许执行边界；P1-P5 本身不作为 B1 创新。
2. **Multi-agent workflow binding:** 本地 Agent 在研究、风险、交易和工具节点间维护任务内一致、跨会话或交易日轮换的金融实体指称。
3. **Audited fail-closed restoration:** 确定性恢复真实身份和 canonical action，歧义、伪造、损坏或过期句柄拒绝执行，并通过故障注入测量 Unsafe Repair。
4. **Joint evaluation protocol:** 在连续金融 Agent 中联合评测原生效用、主动重识别、恢复与执行连续性和在线成本。

## 4. 主实验设计

最终核心矩阵为 `3 Benchmarks x 3 Base LMs x 6 Methods`。原计划的五方法不足以排除“仅靠 episode 轮换的 opaque alias 已经足够”这一解释，因此加入 Episode Alias 强基线。

### Benchmark 原生指标

这一组回答“加入隐私层后，原任务还做得好吗”。指标定义来自各 Benchmark 或其原生回测器，不是 FinScope 提出的新指标：

- **NLPCC 2026 Track 1:** Sharpe（主）、Return、MDD 和 Valid output。
- **StockBench:** Total Return、Sortino、MDD 和 Sharpe。
- **FinVault:** benign task success、attack success、violation-free execution 和 over-refusal。

### FinScope 新增指标

这一组不再把“恢复成功”当成一个笼统数字，而是把保护后闭环的三个关口分别量化，再加隐私和成本。它必须与 Benchmark 原生分数分开报告：

- **决策保持：** `Decision Preservation`，同一 episode 与 Vanilla 对齐后，规范资产和方向（以及可用时的 tool choice）完全一致的比例。
- **协作连续性：** `Reference Continuity`，同一 episode 中至少两个实际角色/视图引用同一 canonical asset 时，是否使用同一 scope handle；只有一个视图的 episode 记为 `N/A`。
- **执行恢复：** `Exact Action Restore`，句柄恢复后的资产、市场、方向和数量/权重与外部输出的本地期望一致，并且通过真实执行器/交易约束的比例。
- **隐私：** `ReID@1`、`Link AUC`。
- **成本：** `Token Delta`、`E2E p95`。

三个闭环指标不是从结果字符串猜出来的：NLPCC runner 在本地保存每个 episode 的 Vanilla action、受保护 action、候选/持仓/交易视图和执行结果；StockBench/FinVault proxy 在本地日志保存 `input_fingerprint`、恢复后的 `decision_fingerprint`、`episode_id`、`role` 和 binding snapshot。聚合脚本按 episode 对齐，缺少多角色视图或真实执行接受信号时输出 `N/A`，不把单次 JSON parse 当作连续性或执行成功。

实验 artifact 保留完整逐日记录、诊断指标、token、延迟和拒绝原因，便于复核与二次分析；论文正文、表格和进度汇报只展示上述每组 2--3 个核心指标。ReID 和金融效用的 95% CI 直接写在对应单元格或脚注中，不为置信区间单独扩列。其余指标只进入机器可读结果和附录。

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

### 近邻工作如何进入主表

主表只加入两个最能解释 B1 差异的工程化近邻基线；它们不是对原论文的逐字复现，而是把可比较的机制接到同一金融 Agent 生命周期中：

| 主表方法 | 近邻方向 | 在本项目中的适配 | 不声称复现的部分 |
| --- | --- | --- | --- |
| Episode Alias | SecureClaw 风格的 opaque handle、session/TTL 生命周期 | 每个交易日轮换不可读句柄，保持同日一致并在本地恢复 | 不复现其完整 trusted executor/PREVIEW-to-COMMIT 实现 |
| LLM Rewrite | PromptGraph 风格的本地敏感 span 改写与恢复 | 在任务模型前做受约束金融标题改写，并记录事实漂移和额外成本 | 不复现其通用 span 图推理和训练流程 |

Global Fixed Alias 作为经典 pseudonym 控制保留；Deletion 和 Vanilla 分别作为隐私下界与任务上界。这样主表中的每个对比方法都对应清晰的机制假设，而不是堆叠相似论文名称。

### Table 1: Benchmark x Base Model x Method 大主表

每行是一个 `Benchmark x Base Model x Method` 实验单元。前四个结果列严格使用该行所属 Benchmark 的原生核心指标，后七个结果列在三个 Benchmark 上统一使用 FinScope 通用指标。原生指标不跨 Benchmark 比大小；通用指标才使用同一列定义比较。

| Benchmark | 原生指标 1 | 原生指标 2 | 原生指标 3 | 原生指标 4 |
| --- | --- | --- | --- | --- |
| NLPCC | Sharpe ↑ | Return ↑ | MDD ↓ | Valid output ↑ |
| StockBench | Total Return ↑ | Sortino ↑ | MDD ↓ | Sharpe ↑ |
| FinVault | Benign Task Success ↑ | Attack Success ↓ | Violation-free Execution ↑ | Over-refusal ↓ |

最终主表列固定为 `4 个 Benchmark 原生指标 + 3 个闭环指标 + 2 个隐私指标 + 2 个成本指标`：

| Benchmark | Base Model | Method | 原生 1 | 原生 2 | 原生 3 | 原生 4 | Decision Preservation ↑ | Reference Continuity ↑ | Exact Action Restore ↑ | ReID@1 ↓ | Link AUC →.5 | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 每个 Benchmark × Base Model × Method | ... | ... | native | native | native | native | closed-loop | closed-loop | closed-loop | privacy | privacy | cost | cost |

`Unsafe Repair` 不再挤进主表，它属于故障注入补表；`Exact Restore` 也不再作为主指标，因为它没有说明动作是否通过本地交易约束。下面保留的旧六指标数字是历史 preliminary snapshot，不能按新的列顺序解读，也不能直接写进论文。

### Archived preliminary six-metric snapshot (do not report as Table 1)

| Benchmark | Base LM | Method | 原生指标 1 | 原生指标 2 | 原生指标 3 | 原生指标 4 | ReID@1 ↓ | Link AUC →.5 | Exact Restore ↑ | Unsafe Repair ↓ | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC | Qwen3.8-27B | Vanilla | 2.426 | 39.45% | 6.88% | 99.18% | 100.00% | 1.000 | -- | -- | ref. | 8.216 s |
| NLPCC | Qwen3.8-27B | Deletion | 0.000 | 0.00% | 0.00% | 0.00% | 100.00% | 1.000 | -- | -- | -3.4% | 7.751 s |
| NLPCC | Qwen3.8-27B | LLM Rewrite | 2.165 | 36.30% | 6.86% | 100.00% | 100.00% | 1.000 | -- | -- | +10.6% | 27.663 s |
| NLPCC | Qwen3.8-27B | Global Alias | 2.264 | 25.28% | 4.43% | 97.53% | 100.00% | 1.000 | 100.00% | 0.00% | +0.1% | 8.180 s |
| NLPCC | Qwen3.8-27B | Episode Alias | 2.260 | 33.14% | 6.29% | 99.59% | 100.00% | 1.000 | 100.00% | 0.00% | +3.6% | 8.364 s |
| NLPCC | Qwen3.8-27B | FinScope P3 | **2.976** | 34.31% | **3.34%** | **100.00%** | **53.20%** | **0.789** | **100.00%** | **0.00%** | **-50.9%** | **7.031 s** |
| NLPCC | DeepSeek V4 Flash | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| NLPCC | DeepSeek V4 Flash | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| NLPCC | DeepSeek V4 Flash | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| NLPCC | DeepSeek V4 Flash | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | DeepSeek V4 Flash | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | DeepSeek V4 Flash | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | GLM-5.1 | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| NLPCC | GLM-5.1 | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| NLPCC | GLM-5.1 | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| NLPCC | GLM-5.1 | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | GLM-5.1 | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| NLPCC | GLM-5.1 | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | Qwen3.8-27B | Vanilla | 4.24% | 2.253 | 2.43% | 1.679 | 100.00% | 1.000 | -- | -- | ref. | 253.267 s |
| StockBench | Qwen3.8-27B | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | Qwen3.8-27B | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | Qwen3.8-27B | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | Qwen3.8-27B | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | Qwen3.8-27B | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | DeepSeek V4 Flash | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| StockBench | DeepSeek V4 Flash | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | DeepSeek V4 Flash | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | DeepSeek V4 Flash | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | DeepSeek V4 Flash | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | DeepSeek V4 Flash | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | GLM-5.1 | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| StockBench | GLM-5.1 | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | GLM-5.1 | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| StockBench | GLM-5.1 | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | GLM-5.1 | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| StockBench | GLM-5.1 | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | Qwen3.8-27B | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| FinVault | Qwen3.8-27B | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | Qwen3.8-27B | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | Qwen3.8-27B | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | Qwen3.8-27B | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | Qwen3.8-27B | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | DeepSeek V4 Flash | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| FinVault | DeepSeek V4 Flash | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | DeepSeek V4 Flash | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | DeepSeek V4 Flash | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | DeepSeek V4 Flash | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | DeepSeek V4 Flash | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | GLM-5.1 | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
| FinVault | GLM-5.1 | Deletion | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | GLM-5.1 | LLM Rewrite | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | TBD | TBD |
| FinVault | GLM-5.1 | Global Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | GLM-5.1 | Episode Alias | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinVault | GLM-5.1 | FinScope P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

`--` 表示该方法没有身份恢复阶段，因此 Exact Restore/Unsafe Repair 不适用。FinScope 的 Unsafe Repair 主值只统计损坏、伪造、过期和越界等应拒绝输入；完整且合法的同类型句柄互换属于意图替换边界，单独在故障注入表披露，不能隐藏在聚合值中。Direct Leak 和 Execution 仍完整记录，但分别作为机制检查和 Benchmark/工作流诊断放入附录，避免与强隐私攻击和恢复指标重复。

#### Table 1 表后指标解释

主表前四个结果列不是一套跨任务分数，而是按行替换为下面对应 Benchmark 的四个原生指标：

| Benchmark | 原生指标列 1 | 原生指标列 2 | 原生指标列 3 | 原生指标列 4 |
| --- | --- | --- | --- | --- |
| NLPCC | Sharpe | Return | MDD | Valid Output |
| StockBench | Total Return | Sortino | MDD | Sharpe |
| FinVault | Benign Task Success | Attack Success | Violation-free Execution | Over-refusal |

原生指标含义与方向：

| 指标 | 含义 | 方向 |
| --- | --- | --- |
| Sharpe | 单位总波动承担获得的收益，衡量风险调整后的回报 | 越高越好 |
| Return / Total Return | 测试期初始资产到最终资产的累计收益率 | 越高越好 |
| MDD | 从历史峰值到随后谷底的最大跌幅 | 越低越好 |
| Valid Output | 满足 NLPCC 输出格式、资产范围和数值约束的比例 | 越高越好 |
| Sortino | 只将下行波动视为风险的风险调整收益 | 越高越好 |
| Benign Task Success | FinVault 正常合法请求被正确完成的比例 | 越高越好 |
| Attack Success | 攻击成功诱导 Agent 执行目标危险行为的比例 | 越低越好 |
| Violation-free Execution | 执行结束后未触发违规工具调用或危险业务状态的比例 | 越高越好 |
| Over-refusal | 正常合法请求被错误拒绝的比例 | 越低越好 |

主表后七列由 FinScope 评测协议统一补充，在 NLPCC、StockBench、FinVault 三个 Benchmark 上定义完全不变；它们不替代 Benchmark 原生指标：

| 指标 | 含义 | 方向 |
| --- | --- | --- |
| Decision Preservation | 同一 episode 中，保护方法与 Vanilla 的 canonical asset、动作方向以及可用时的 tool choice 完全一致率；NLPCC 当前没有 tool trace，因此只报告 asset+direction | 越高越好 |
| Reference Continuity | 至少两个真实角色/视图共同引用某资产时，所有视图是否使用同一 scope handle；没有两个视图的 episode 不进入分母 | 越高越好；同时报告覆盖数 |
| Exact Action Restore | 外部 action 的句柄恢复为唯一 canonical asset，市场/方向/数量/权重等执行字段保持一致，并被本地执行器接受 | 越高越好 |
| ReID@1 | 攻击者依据匿名 trace 和允许的公开侧信息，第一名猜中真实资产身份的比例 | 越低越好；同时报告候选池随机基线 |
| Link AUC | 攻击者判断不同 scope/日期的两个匿名对象是否为同一真实实体的能力 | 越接近 0.5 越好 |
| Token Delta | 相对同 Benchmark、同模型 Vanilla 的输入输出 token 增减比例 | 越低越好；负数表示节省 |
| E2E p95 | 从隐私预处理、模型推理到恢复校验完成的端到端延迟第 95 百分位 | 越低越好 |

`Unsafe Repair` 是故障注入补表指标，不进入主表；它统计本应拒绝的损坏、伪造、过期或歧义输出被错误接受的比例，目标为 0。

### 三个闭环指标的实际实现

**Decision Preservation。** 每个方法和 Vanilla 使用同一个 episode key（NLPCC 是交易日；StockBench/FinVault 是 `episode_id + role + input_fingerprint`）。先把 action 中的别名在本地恢复成 canonical asset，再只比较真正表达决策的字段：资产、方向和可用时的 tool choice；数量、金额和权重不放进这个指标，而交给 Exact Action Restore。分母是 Vanilla 的全部对齐 episode，protected 输出解析失败或被拒绝也算未保持。NLPCC 的温度为 0、`do_sample=False`，因此这个比较不是把随机波动误当隐私影响；外部 proxy 用恢复后 action 的本地 hash 对齐，不把敏感 response 写进摘要。

**Reference Continuity。** 不能拿一个句柄查表成功率代替多 Agent 连续性。NLPCC runner 将候选池、持仓和返回 action 分别记录为 research/risk/trade 三个真实视图；某资产至少出现在两个视图时，检查它们是否使用同一个 scope handle。StockBench/FinVault 直接从 proxy audit 的 `episode_id`、`role` 和 `bindings` 聚合：同一 episode 至少有两个角色才进入分母；同一角色在多个请求中发生映射漂移也算失败。只有单个角色或单个视图的 episode 报 `N/A` 并给出 coverage，不能报 100%。

**Exact Action Restore。** 先保存模型返回的匿名 action，再由本地 resolver 恢复 asset；随后对 asset/market/side/quantity/amount/percentage/weight/price 等执行字段做规范化比较。最后必须调用 benchmark 的真实 action validator/executor，现金不足、空仓卖出、权重越界或市场约束失败都使该 episode 记为 0。也就是说，`valid JSON` 和“句柄存在”都不够；只有字段完整、映射唯一且执行器接受，才记为 1。对于没有恢复边界的 Vanilla/Deletion，指标为 `N/A`，不把直接使用真实 ID 或不可恢复删除伪装成成功。

#### 任务模型与攻击者模型

- **任务模型（victim/task model）**生成金融决策或工具动作。当前已完成单元使用 Qwen3.8-27B。
- **当前主攻击者不是语言模型。** `ReID@1` 和 `Link AUC` 由确定性的公开证券主表与行情属性匹配 oracle 计算；它不调用 Qwen、DeepSeek 或 GLM，因此与任务模型独立，所有方法面对完全相同的攻击规则和侧信息。
- **FinVault 的主攻击同样不需要攻击模型。** Benchmark 提供固定的对抗提示，由作为 victim 的任务模型响应并调用沙箱工具；`Attack Success` 衡量这些提示是否诱导任务模型触发危险状态。只有生成或改写新攻击提示时才需要单独的 attacker model。
- **LLM attacker 是单独的敏感性实验。** 后续分别使用 Qwen、DeepSeek 和 GLM 读取相同匿名 trace，并显式记录 `victim_model`、`attacker_model`、候选池、查询预算和公开侧信息。即使两者都选 Qwen，也必须作为两个独立角色和调用统计，不能写成“任务模型自己攻击自己”。
- 主表中的当前攻击结果必须标注 `attacker=public-side-information oracle`；模型攻击结果不进入 S1-S5，只在附录敏感性分析中单独记录，不能替换 oracle 主结果。

## 5. 补充实验表格

**当前执行版已移到 [`coling_supplemental_experiments.md`](coling_supplemental_experiments.md)。** 该文档按现在确定的三组八项实验给出完整表格：动态披露三项、长程替换与效用保持三项、本地小模型选择和组件消融各一项。下面原有的 S1-S5 是早期方案，保留作历史记录，不再作为当前实验清单或论文表格。

### 早期补充表（历史记录，不执行）

Table 1 已经回答“不同 Benchmark、任务基座和方法的最终效用/隐私/恢复/总成本是多少”。下面的补充表不再重复 Table 1 的任何列，也不重新排列主表的六种方法。所有补充实验固定在 **NLPCC 2026 Track 1 public A-set + Qwen3.8-27B 任务模型**，只改变一个 B1 机制因素；尚未通过真实测试窗口的单元统一写 `TBD`，绝不以 smoke 或旧版结果填充。

### Table S1: 本地隐私 Agent 选型（10 个模型，均 ≤4B）

**服务的故事：** FinScope 是一个额外的本地智能体，而不是把任务模型再复制一遍。本表证明识别、规划和审计可以由小模型承担，并用本地 Agent 自己的可靠性和开销锁定主模型；主表中的金融收益和原生 Valid 不在此重复。

任务模型固定为 Qwen3.8-27B；使用官方 NLPCC 2026 Track 1 public A-set，按时间顺序固定前 20 个交易日为开发集，其余交易日为测试集。10 个 instruction-tuned 本地模型共用同一 JSON 协议、P3、候选池、调用预算和三个角色（recognizer/planner/auditor）。严格模式禁止整套 deterministic fallback；字段级安全规范化单独计入 `planner_repairs`。

模型清单和下载状态见 [`benchmarks/local_privacy_models.json`](../benchmarks/local_privacy_models.json)。

| Local privacy model | Size | Strict planner valid ↑ | Recognizer fail ↓ | Auditor fail ↓ | Whole fallback ↓ | Planner repair rate ↓ | Calls / asset ↓ | Local Agent p95 ↓ | Availability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3.5-0.8B | 0.8B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Qwen3.5-2B | 2B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Qwen3.5-4B | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Qwen3-0.6B | 0.6B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | download required |
| Qwen3-1.7B | 1.7B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | download required |
| Llama-3.2-1B-Instruct | 1B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Llama-3.2-3B-Instruct | 3B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Gemma-3-1B-it | 1B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Gemma-3-4B-it | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ready |
| Gemma-4-4B-it | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | alias required |

预注册选择规则：先要求严格 planner valid ≥99%、recognizer/auditor failure = 0、fallback = 0；满足者中优先本地 p95 和 token 更低者，再检查开发集 NLPCC Valid。开发集只用于选主方法，测试集不能反选。当前已有的双资产和单日 smoke 只用于排查服务，不填入这张正式表，也不作为论文百分比。

小模型指标含义：`Strict planner valid` 是不调用整套 deterministic fallback 时产生合法、可验证计划的比例；`Whole fallback` 是整条链路退回确定性计划的次数；`Planner repair rate` 只计字段级安全规范化，不把失败伪装成成功；`Calls / asset` 和 `Local Agent p95` 只统计本地 Agent，不包含任务模型端到端延迟。

### Table S2: P1-P5 语义预算与本地决策

**服务的故事：** B1 不是只把名称换成随机串，而是由本地 Agent 按任务需要选择最小必要语义。本表回答“每个披露级别实际释放了什么、验证器是否接受、代价如何”，不重复主表的 Sharpe、ReID@1 或 Link AUC。

| Level | Allowed master fields | Mean disclosed fields / asset ↓ | Mean disclosure tokens ↓ | Direct-identity guard rejects ↑ | Planner repair rate ↓ | Cache hit rate ↑ | Trade escalation rate ↓ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P2 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P4 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| P5 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Adaptive (dev calibrated) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

`Allowed master fields` 是证券主表中允许外发的字段集合；`Direct-identity guard rejects` 统计本地验证器拦截模型直接复述真实身份的次数；`Trade escalation` 是交易动作触发更严格披露或人工/代码校验的比例。测试集不能反向选择 P-level。

### Table S3: 多 Agent 作用域生命周期

**服务的故事：** FinScope 是多智能体系统里新增的本地 Agent。研究、风控、交易节点需要在同一任务内指向同一资产，但下一交易日不能继续沿用旧身份。本表只测协作和生命周期性质，不重复主表的跨方法 Link AUC。

| Protocol | Same-day cross-role binding agreement ↑ | Cross-scope handle reuse ↓ | Stale-handle rejection ↑ | Unauthorized role access blocked ↑ | Rotation completion ↑ | Mapping lifetime (days) ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Global fixed alias | TBD | TBD | TBD | TBD | TBD | TBD |
| Episode opaque alias | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope handles-only | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope full (P3) | TBD | TBD | TBD | TBD | TBD | TBD |

`Same-day cross-role binding agreement` 检查 research/risk/trade 是否得到同一 scope 内同一 canonical entity；`Cross-scope handle reuse` 检查旧句柄是否在新交易日或新任务中复用；`Mapping lifetime` 记录本地映射保留时间。该表解释“为什么要有独立本地 Agent 和 scope”，不是再次报告任务收益。

### Table S4: 真实 Portfolio Trace 故障边界

**服务的故事：** 恢复不是文本后处理，而是交易前安全边界。本表从真实 NLPCC 模型输出和对应 portfolio state 注入故障，报告系统如何发现、拒绝并中断执行；主表只保留聚合的 Exact Restore/Unsafe Repair，因此不在这里重复这两列。

| Fault injected into accepted trace | Detection stage | Correct-reject reason code coverage ↑ | State equivalence after accepted clean trace ↑ | Execution interruption on unsafe trace ↑ | Manual escalation rate ↑ |
| --- | --- | ---: | ---: | ---: | ---: |
| Truncated handle | binding resolver | TBD | TBD | TBD | TBD |
| Fabricated handle | binding resolver | TBD | TBD | TBD | TBD |
| Previous-day handle | scope validator | TBD | TBD | TBD | TBD |
| Same-type handle swap | ambiguity auditor | TBD | TBD | TBD | TBD |
| Descriptor without handle | action validator | TBD | TBD | TBD | TBD |
| Schema / numeric overflow | business validator | TBD | TBD | TBD | TBD |

`Reason code coverage` 要求每个拒绝都能落到可审计的错误类别；`State equivalence` 只对未注入的 clean trace 检查恢复后 portfolio state 是否等价；`Execution interruption` 检查危险输入是否在交易提交前被截断。双资产 smoke 和单元测试不填入此表。

### Table S5: B1 组件必要性消融

**服务的故事：** 该表把 FinScope 的闭环拆成可解释的必要组件，回答“收益/隐私变化不是某个无关开关造成的”。所有变体固定同一任务模型、数据和 P3，只删除一个组件；不重复主表结果，而记录组件对安全事件的捕获类型。

| Variant | Removed component | Direct identity caught ↑ | Invalid master field caught ↑ | Scope violation caught ↑ | Ambiguity escalated ↑ | Pre-trade invalid action blocked ↑ | Failure code completeness ↑ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full FinScope | none | TBD | TBD | TBD | TBD | TBD | TBD |
| No semantic planner | P1-P5 planner | TBD | TBD | TBD | TBD | TBD | TBD |
| No scope rotation | day/task rotation | TBD | TBD | TBD | TBD | TBD | TBD |
| No security-master validation | fact/type validator | TBD | TBD | TBD | TBD | TBD | TBD |
| No restoration auditor | ambiguity auditor | TBD | TBD | TBD | TBD | TBD | TBD |

该表的因变量是安全门控事件和错误分类覆盖率，而不是主表的金融分数；若某变体导致任务完全无法运行，记录为机制失败并在正文解释，不用零收益制造“更安全”的结论。

### Supplement map: Table S1-S5 与论文故事的对应关系

| Supplement | 独立回答的问题 | 支撑的故事段落 | 不重复 Table 1 的原因 |
| --- | --- | --- | --- |
| S1 | 哪个 ≤4B 本地模型足以运行隐私 Agent？ | 本地 Agent 可行性与模型选择 | 只报告本地 Agent 可靠性/调用开销 |
| S2 | P1-P5 实际释放哪些金融语义？ | 最小必要语义披露 | 只报告字段预算和验证行为 |
| S3 | 多 Agent 如何共享同一指称并跨日轮换？ | 作用域生命周期与协作连续性 | 只报告绑定、轮换和权限事件 |
| S4 | 损坏输出为何不能直接进入交易？ | 恢复即执行安全边界 | 只报告故障检测、状态等价和中断 |
| S5 | 哪些组件是闭环成立的必要条件？ | 机制因果解释 | 只报告安全门控捕获类型 |

这张对应关系表本身是写作索引，不是实验结果表；它防止把 Table 1 的指标复制到补充材料。

### Table S1-S5 的统一实验边界

以下实验都使用同一 NLPCC 2026 Track 1 public A-set、官方 DataLoader、同一 Qwen3.8-27B 任务模型和 Table S1 选出的本地模型。除非明确写出开发集，所有数字均来自未参与模型选择的测试交易日；不使用双资产 toy、静态伪造输入或单元测试百分比。

| ID | Formal protocol on NLPCC | Controlled change | Primary report | B1 claim |
| --- | --- | --- | --- | --- |
| S1 | 10-model local Agent ablation on fixed 20-day development prefix; selected model replayed on held-out days | only local recognizer/planner/auditor model changes | strict planner validity, failures, fallback, repairs, local calls and p95 | 本地小模型足以承担隐私 Agent，且选择不依赖测试收益 |
| S2 | Full held-out daily replay at P1/P2/P3/P4/P5 with selected model | only disclosure level changes | allowed fields, disclosed tokens, verifier decisions, repair/cache/escalation behavior | 语义披露是可控预算，而非随机字符串替换 |
| S3 | Three logical roles (research/risk/trade) share a scope within each day and rotate at day boundary; replay real candidate/news/action traces | global alias vs episode alias vs FinScope lifecycle | cross-role agreement, scope reuse, stale rejection, role authorization, rotation completion | 生命周期绑定支持多 Agent 连续协作而非只替换字符串 |
| S4 | Inject faults into accepted real FinScope outputs and replay the corresponding NLPCC action at its recorded portfolio state | clean output vs truncated/forged/stale/swapped/schema/numeric faults | reason-code coverage, state equivalence, execution interruption, escalation | 恢复是交易前安全边界，异常结果 fail-closed |
| S5 | Re-run the same held-out traces after removing one FinScope component | planner, scope rotation, security master, or auditor removal | component-specific security event capture and gate coverage | 每个组件对闭环安全有可归因作用 |

S3 的攻击仍使用公开证券主表/行情属性 oracle；S4 必须从真实模型输出和真实 portfolio trace 生成扰动。攻击者能力、查询预算、候选池规模和 side-information 敏感性不进入正文补充表；如审稿人要求，放到附录并只报告相对主攻击的变化，不能再复制 Table 1 的完整指标矩阵。

## 6. 实验执行清单

### P0: 论文主张成立前必须完成

1. 实现并运行 Episode Alias 强基线，修正 baseline 命名。
2. 实现同基座 LLM Rewrite，并将额外调用、token、延迟和事实漂移计入。
3. 按 `benchmarks/local_privacy_models.json` 在 NLPCC 固定开发窗口跑完 10 个 ≤4B 本地模型，按预注册规则锁定主方法模型。
4. 用锁定的小模型完成 Qwen3.8-27B x NLPCC 的六方法全量重放，再决定是否扩展到 StockBench/FinVault。
5. 建立本地 attack ground truth，运行公开侧信息 ReID、候选池/持仓恢复、动作推断和 Link AUC。
6. 完成 Table S2-S4：P1-P5 测试集语义预算、三角色作用域回放、真实 portfolio trace 故障注入。
7. 为主要 rate 报告 95% CI；金融序列采用 paired moving-block bootstrap，不能把交易日当独立样本做普通 t-test。

### P1: COLING 完整性所需

8. 在 NLPCC 主平台完成 Table S1-S5 的五项正交补充实验。
9. 运行 Adaptive，并只在开发集标定、测试集报告。
10. 记录 detector/planner/auditor 调用、缓存、probe、GPU 显存/能耗和 API 成本。
11. 只有 S1-S4 完成后，才把同一协议迁移到 StockBench/FinVault；迁移结果单独成表，不与 NLPCC 硬平均。

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

> On a full-year NLPCC public A-set replay with Qwen3.8-27B, FinScope P3 reduces public-oracle asset ReID@1 from 100% to 53.2% and adjacent-day Link AUC from 1.000 to 0.789, while achieving a 2.976 Sharpe ratio and 34.31% cumulative return. P5 reaches the random-guess privacy baseline at lower utility, exposing a measurable privacy-utility frontier rather than complete anonymity.

## 9. 当前结论边界

当前已完成 `1/9` 个 Benchmark x Base LM 单元，NLPCC x Qwen3.8-27B 的 `6/6` 方法、P1-P5、公开行情 oracle 隐私攻击、故障注入和 10,000 次 paired block bootstrap 均已完成。可以主张端到端可运行、直接标识不外发、P1-P5 存在可测的隐私-效用前沿，以及损坏/伪造/过期输入 fail-closed。不能主张三模型或三 Benchmark 泛化，也不能声称 P3 完全匿名；完整合法句柄互换仍是需要明确披露的意图替换边界。
