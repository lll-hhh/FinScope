# FinScope: COLING 论文故事、实验清单与表格草案

更新日期：2026-08-22。`Measured` 表示已有真实实验结果，`TBD` 表示必须补跑，`--` 表示不适用。当前结果来自 NLPCC 2026 Track 1 public A-set 的全年重放，不是官方榜单提交，也不是最终多模型统计结果。

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
- 相对 Vanilla，FinScope 保留 87.0% 累计收益；Sharpe 为 2.976（Vanilla 2.426），MDD 为 3.34%（Vanilla 6.88%）。
- Deletion 的执行成功率为 0%；Global Alias 保留部分效用，但跨日链接仍为 100%。
- 公开行情 oracle 下，FinScope P3 将 ReID@1 从其他方法的 100% 降到 53.20%，Link AUC 从 1.000 降到 0.789；这说明风险下降但远未完全匿名。P5 达到随机基线，但金融效用低于 P3。
- FinScope 的执行成功率为 99.2%，输入 token 比 Vanilla 少 50.9%，端到端 p95 从 8.216 秒降到 7.031 秒。

这些结果证明端到端闭环可行，但尚不足以支持“抵抗语义重识别”或“跨模型、跨任务泛化”的最终主张。

## 3. 预期贡献

1. **Lifecycle-bound semantic handles:** 将最小必要金融语义与不可跨 scope 复用的类型化句柄绑定，而非只删除或全局替换身份。
2. **Executable privacy mediation:** 把隐私保护扩展到 LLM 输出、工具参数、本地恢复和真实环境状态转换。
3. **Audited fail-closed restoration:** security-master 验证描述，确定性恢复真实身份，歧义或旧句柄拒绝执行。
4. **Evaluation protocol:** 在连续金融 Agent 中联合评测原生效用、主动隐私攻击、恢复连续性和在线成本。

## 4. 主实验设计

最终核心矩阵为 `3 Benchmarks x 3 Base LMs x 6 Methods`。原计划的五方法不足以排除“仅靠 episode 轮换的 opaque alias 已经足够”这一解释，因此加入 Episode Alias 强基线。

### Benchmark 原生指标

这一组回答“加入隐私层后，原任务还做得好吗”。指标定义来自各 Benchmark 或其原生回测器，不是 FinScope 提出的新指标：

- **NLPCC 2026 Track 1:** Sharpe（主）、Return、MDD 和 Valid output。
- **StockBench:** Total Return、Sortino、MDD 和 Sharpe。
- **FinVault:** benign task success、attack success、violation-free execution 和 over-refusal。

### FinScope 新增指标

这一组回答“隐私层是否真正保护身份、能否安全恢复、代价多大”，必须与 Benchmark 原生分数分开报告：

- **隐私：** ReID@1、Link AUC。
- **连续性与恢复安全：** Exact Restore、Unsafe Repair。
- **系统成本：** Token Delta、E2E p95。

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

### Table 1: Benchmark x Base Model x Method 大主表

每行是一个 `Benchmark x Base Model x Method` 实验单元。前四个结果列严格来自上游 Benchmark，后六个结果列严格由 FinScope 评测协议补充：

| Benchmark | B1 原生主指标 | B2 原生效用 | B3 原生风险/安全 | B4 原生辅助 |
| --- | --- | --- | --- | --- |
| NLPCC | Sharpe ↑ | Return ↑ | MDD ↓ | Valid output ↑ |
| StockBench | Total Return ↑ | Sortino ↑ | MDD ↓ | Sharpe ↑ |
| FinVault | Benign Task Success ↑ | Attack Success ↓ | Violation-free Execution ↑ | Over-refusal ↓ |

六个新增指标固定为：隐私 `ReID@1 / Link AUC`，恢复安全 `Exact Restore / Unsafe Repair`，成本 `Token Delta / E2E p95`。因此所有 Benchmark 和模型都使用同一套新增评测口径。

| Benchmark | Base LM | Method | B1 | B2 | B3 | B4 | ReID@1 ↓ | Link AUC →.5 | Exact Restore ↑ | Unsafe Repair ↓ | Token Δ ↓ | E2E p95 ↓ |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC | Qwen3.8-27B | Vanilla | 2.426 | 39.45% | 6.88% | 99.18% | 100.00% | 1.000 | -- | -- | ref. | 8.216 s |
| NLPCC | Qwen3.8-27B | Deletion | 0.000 | 0.00% | 0.00% | 0.00% | 100.00% | 1.000 | -- | -- | -3.4% | 7.751 s |
| NLPCC | Qwen3.8-27B | LLM Rewrite | 2.165 | 36.30% | 6.86% | 100.00% | 100.00% | 1.000 | -- | -- | +10.6% | 27.663 s |
| NLPCC | Qwen3.8-27B | Global Alias | 2.264 | 25.28% | 4.43% | 97.53% | 100.00% | 1.000 | TBD | TBD | +0.1% | 8.180 s |
| NLPCC | Qwen3.8-27B | Episode Alias | 2.260 | 33.14% | 6.29% | 99.59% | 100.00% | 1.000 | TBD | TBD | +3.6% | 8.364 s |
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
| StockBench | Qwen3.8-27B | Vanilla | TBD | TBD | TBD | TBD | TBD | TBD | -- | -- | ref. | TBD |
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

#### Table 1 指标解释

前四列 `B1--B4` 是 Benchmark 原生指标槽位，含义随 Benchmark 改变；它们只用于比较同一 Benchmark 内不同模型和方法，不能跨 Benchmark 比大小：

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

后六列由 FinScope 评测协议统一补充，在三个 Benchmark 上定义不变：

| 指标 | 含义 | 方向 |
| --- | --- | --- |
| ReID@1 | 攻击者依据匿名 trace 和允许的公开侧信息，第一名猜中真实资产身份的比例 | 越低越好；同时报告候选池随机基线 |
| Link AUC | 攻击者判断不同 scope/日期的两个匿名对象是否为同一真实实体的能力 | 越接近 0.5 越好 |
| Exact Restore | 匿名模型输出恢复后，实体、动作和数值与本地 ground truth 完全一致的比例 | 越高越好 |
| Unsafe Repair | 对本应拒绝的损坏、伪造、过期或歧义输出，系统错误接受并恢复成另一动作的比例 | 越低越好，目标为 0 |
| Token Delta | 相对同 Benchmark、同模型 Vanilla 的输入输出 token 增减比例 | 越低越好；负数表示节省 |
| E2E p95 | 从隐私预处理、模型推理到恢复校验完成的端到端延迟第 95 百分位 | 越低越好 |

#### 任务模型与攻击者模型

- **任务模型（victim/task model）**生成金融决策或工具动作。当前已完成单元使用 Qwen3.8-27B。
- **当前主攻击者不是语言模型。** `ReID@1` 和 `Link AUC` 由确定性的公开证券主表与行情属性匹配 oracle 计算；它不调用 Qwen、DeepSeek 或 GLM，因此与任务模型独立，所有方法面对完全相同的攻击规则和侧信息。
- **FinVault 的主攻击同样不需要攻击模型。** Benchmark 提供固定的对抗提示，由作为 victim 的任务模型响应并调用沙箱工具；`Attack Success` 衡量这些提示是否诱导任务模型触发危险状态。只有生成或改写新攻击提示时才需要单独的 attacker model。
- **LLM attacker 是单独的敏感性实验。** 后续分别使用 Qwen、DeepSeek 和 GLM 读取相同匿名 trace，并显式记录 `victim_model`、`attacker_model`、候选池、查询预算和公开侧信息。即使两者都选 Qwen，也必须作为两个独立角色和调用统计，不能写成“任务模型自己攻击自己”。
- 主表中的当前攻击结果必须标注 `attacker=public-side-information oracle`；模型攻击结果只进入攻击强度补充表，不能替换 oracle 主结果。

## 5. 补充实验表格

### Table 2: NLPCC 原生金融效用（Measured）

| Method | Return ↑ | Sharpe ↑ | MDD ↓ |
| --- | ---: | ---: | ---: |
| Vanilla | **39.45%** | **2.426** | 6.88% |
| Deletion | 0.00% | 0.000 | 0.00% |
| LLM Rewrite | 36.30% | 2.165 | 6.86% |
| Global Alias | 25.28% | 2.264 | **4.43%** |
| Episode Alias | 33.14% | 2.260 | 6.29% |
| FinScope P3 | 34.31% | **2.976** | **3.34%** |

Deletion 的零回撤不是优势，而是从未执行交易。正文不能将其加粗或描述为低风险方法。

### Table 3: 主动隐私攻击

攻击者可观察全部匿名 prompt/output、跨 Agent trace、跨日 trace，以及公开新闻和行情；不可读取本地映射。所有攻击指标报告均值、95% CI、随机基线和候选池规模。

| Method | Direct Leak ↓ | ReID@1 ↓ | Link AUC →.5 |
| --- | ---: | ---: | ---: |
| Vanilla | 100.0% | 100.00% | 1.000 |
| Deletion | 0.0% | 100.00% | 1.000 |
| LLM Rewrite | 0.0% | 100.00% | 1.000 |
| Global Alias | 0.0% | 100.00% | 1.000 |
| Episode Alias | 0.0% | 100.00% | 1.000 |
| FinScope P3 | **0.0%** | **53.20%** | **0.789** |

当前另有一个不依赖攻击模型的诊断指标：Global Alias 的跨日唯一字符串链接率为 100%，FinScope 为 0%。它只能作为机制 sanity check，不能替代 Link AUC。

### Table 4: 恢复与流程连续性

| Method | Execution ↑ | Exact Restore ↑ | Unsafe Repair ↓ |
| --- | ---: | ---: | ---: |
| Vanilla | 98.8% | -- | -- |
| Deletion | 0.0% | -- | -- |
| LLM Rewrite | 100.0% | -- | -- |
| Global Alias | 97.5% | TBD | TBD |
| Episode Alias | 99.2% | TBD | TBD |
| FinScope P3 | 99.2% | **100.0%** | **0.0%** |

自然运行中 FinScope 有 6 次 malformed JSON、3 次 `direct_identity_output` 审计拒绝和 1 次卖出空持仓。Exact Restore、State Equivalence 和 Unsafe Repair 必须通过保存本地 ground truth 和故障注入正式评分，不能用 `Valid/Parsed` 代替。

### Table 5: P1-P5 隐私-效用曲线

| Level | Semantic fields | Sharpe ↑ | ReID@1 ↓ | Link AUC →.5 |
| --- | --- | ---: | ---: | ---: |
| P1 | 最丰富的受验证语义 | 2.047 | 93.27% | 0.872 |
| P2 | 较丰富语义 | 1.934 | 88.10% | 0.871 |
| P3 | 标准语义 | **2.976** | 53.20% | 0.789 |
| P4 | 粗粒度语义 | 1.434 | 24.24% | 0.647 |
| P5 | 最小语义/执行句柄 | 1.856 | **9.09%** | **0.500** |
| Adaptive | 开发集标定的最小可用级别 | TBD | TBD | TBD |

P1-P5 的具体字段定义应在论文方法表中固定，测试集上不能根据收益反向挑选等级。Adaptive 必须仅在开发集标定。

### Table 6: 恢复鲁棒性与故障注入

| Perturbation | Exact Restore ↑ | Correct Reject ↑ | Unsafe Repair ↓ |
| --- | ---: | ---: | ---: |
| Prefix/suffix/quotes/brackets | 100.0% | -- | 0.0% |
| Descriptor without handle | 0.0% | 100.0% | 0.0% |
| Swap two same-type handles | 0.0% | 0.0% | 100.0% |
| Truncated/fabricated handle | 0.0% | 100.0% | 0.0% |
| Stale previous-day handle | 0.0% | 100.0% | 0.0% |
| Coreference points to wrong asset | TBD | TBD | TBD |
| Partial/malformed JSON | 0.0% | 100.0% | 0.0% |
| Out-of-range amount/weight | 0.0% | 100.0% | 0.0% |
| Tool schema drift | TBD | TBD | TBD |

单元测试只证明预期的软件分支，不应作为论文百分比。正式实验应从真实模型输出生成扰动，并保留可判定的 ground truth。

### Table 7: Privacy Agent 消融

| Variant | Sharpe ↑ | ReID@1 ↓ | Unsafe Repair ↓ |
| --- | ---: | ---: | ---: |
| Full FinScope | 2.976 | 53.20% | 0.0% |
| - semantic descriptors, handles only | TBD | TBD | TBD |
| - scope rotation | TBD | TBD | TBD |
| - security-master validation | TBD | TBD | TBD |
| - restoration auditor | TBD | TBD | TBD |
| - coreference reuse | TBD | TBD | TBD |
| Always scan | TBD | TBD | TBD |
| Gated scan | TBD | TBD | TBD |
| - task cache | TBD | TBD | TBD |

最关键的两项是 Episode Alias 与 `handles only`。它们用于证明收益来自受验证语义，而隐私与连续性来自生命周期和恢复机制，而不是某一个字符串格式。

### Table 8: 成本与延迟（Measured）

| Method | Token Δ ↓ | E2E p95 ↓ |
| --- | ---: | ---: |
| Vanilla | ref. | 8.216 s |
| Deletion | -3.4% | **7.751 s** |
| LLM Rewrite | +10.6% | 27.663 s |
| Global Alias | +0.1% | 8.180 s |
| Episode Alias | +3.6% | 8.364 s |
| FinScope P3 | **-50.9%** | **7.031 s** |

本表只报告读者最容易解释的 token 增量和端到端尾延迟。detector/planner/auditor 调用次数、cache hit、probe、峰值显存、API 金额和 GPU 能耗保留在机器可读 artifact；仅在成本异常或审稿人要求时进入附录。

### Table 9: 攻击强度与累计泄露

| Setting | Values | ReID@1 ↓ | Link AUC →.5 |
| --- | --- | ---: | ---: |
| Query budget | 1 / 3 / 5 / 10 | TBD | TBD |
| Candidate pool | 20 / 100 / 500 / full | TBD | TBD |
| Observable agents | research / +risk / +trade | TBD | TBD |
| Public side info | none / news / news+prices | TBD | TBD |
| Attack model | Qwen / DeepSeek / GLM | TBD | TBD |

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

> On a full-year NLPCC public A-set replay with Qwen3.8-27B, FinScope P3 reduces public-oracle asset ReID@1 from 100% to 53.2% and adjacent-day Link AUC from 1.000 to 0.789, while achieving a 2.976 Sharpe ratio and 34.31% cumulative return. P5 reaches the random-guess privacy baseline at lower utility, exposing a measurable privacy-utility frontier rather than complete anonymity.

## 9. 当前结论边界

当前已完成 `1/9` 个 Benchmark x Base LM 单元，NLPCC x Qwen3.8-27B 的 `6/6` 方法、P1-P5、公开行情 oracle 隐私攻击、故障注入和 10,000 次 paired block bootstrap 均已完成。可以主张端到端可运行、直接标识不外发、P1-P5 存在可测的隐私-效用前沿，以及损坏/伪造/过期输入 fail-closed。不能主张三模型或三 Benchmark 泛化，也不能声称 P3 完全匿名；完整合法句柄互换仍是需要明确披露的意图替换边界。
