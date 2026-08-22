# FinScope：面向金融 Agent 的本地隐私 Agent

FinScope 解决一个很具体的问题：金融 Agent 需要把新闻、行情、候选池和持仓交给大模型分析，但这些内容会暴露真实资产和交易意图；简单删除资产名又会让研究、风控、交易和工具执行无法确认它们讨论的是不是同一只资产。

本项目在金融 Agent 与外部模型之间放置一个可信的**本地隐私 Agent**。它自动发现敏感信息、生成不同信息量的描述、维护临时绑定表，并在外部模型返回后恢复真实参数、审计歧义、校验交易动作。核心目标是：

- **任务内一致**：同一研究—风控—交易流程中的同一资产使用同一句柄；
- **任务外不可关联**：任务、会话或交易日结束后清除映射并轮换句柄；
- **语义可调**：不是只能把“贵州茅台”改成无意义代码，也可以改成“白酒股票”“消费股票”等不同信息量的描述；
- **恢复可执行**：外部输出只能在本地恢复，歧义、旧句柄和非法交易指令默认阻断。

> 本仓库用于学术研究和历史回测，不执行真实交易，也不构成投资建议。

## 1. 先看懂整体流程

```text
原始金融请求
   │
   ├─ 1. 本地证券主表/已有映射先替换已知实体
   ├─ 2. 本地模型只检查剩余文本，发现新实体、代词、动作、关系和意图
   ├─ 3. Privacy Agent 生成 P1-P5 描述并绑定唯一句柄
   ▼
<fin-ref id="FS_ASSET_...">白酒股票</fin-ref>
   │
   ├─ 4. 外部金融模型分析匿名内容
   ▼
匿名模型输出
   │
   ├─ 5. 本地代码按句柄确定性恢复
   ├─ 6. 本地恢复审计 Agent 检查指代、语义漂移和句柄丢失
   ├─ 7. 本地校验资产、方向、数量和权重
   ▼
回测 / mock 工具 / paper-trading 执行器
```

这里使用“双表示”，而不是只发一个纯代号：

```text
<fin-ref type="asset" id="FS_ASSET_7KQ9ABCD">白酒股票</fin-ref>
```

`白酒股票`给外部模型保留决策所需的金融语义；`FS_ASSET_7KQ9ABCD`不包含真实身份，只负责本地精确恢复。两只白酒股票可以有相同描述，但句柄一定不同，因此不会把两只资产恢复成同一个。模型如果删掉句柄、编造句柄或把不同资产合并，恢复审计会要求重试或阻断执行。

## 2. P1-P5 五级披露

用户可以固定选择等级；自适应模式必须先用实验数据标定，代码不会凭感觉自动降低保护强度。

| 等级 | 示例 | 保留信息 | 适合阶段 |
| --- | --- | --- | --- |
| P1 | 大盘白酒股票 | 规模、细分行业、资产类型 | 细粒度研究 |
| P2 | 白酒股票 | 细分行业、资产类型 | 行业比较 |
| P3 | 消费股票 | 一级行业、资产类型 | 常规研究/风控 |
| P4 | A股股票 | 市场、资产类型 | 只需市场约束 |
| P5 | 股票 | 仅资产类型 | 执行前或最高保护 |

五级描述由本地模型提出，但不能直接采用。代码会用本地证券主表检查：描述是否包含真实名称/代码、字段是否属于该级允许集合、行业和市场是否真实、模型是否编造“龙头”“利好”等事实。校验失败就退回确定性安全描述。已生成的 `(资产, 主表版本, 任务目的)` 结果会缓存，资产没有变化时不会反复调用模型。

## 3. 已经实现了什么

- 资产、机构、账户、组合、策略、代词、动作、关系和意图的本地识别接口；
- security master 确定性首轮替换 + 本地模型残余扫描；
- 连续空扫描后 cooldown、模板缓存、风险唤醒和周期抽检；
- P1-P5 自动描述、事实校验、缓存和用户选择；
- 任务/会话/交易日作用域内稳定、作用域外自动轮换的双向映射；
- XML 式 typed handle，支持相同行业描述下的多资产无冲突恢复；
- JSON、列表、字典键、普通文本及常见前后缀的确定性恢复；
- 旧句柄、未知句柄、描述与句柄不匹配、描述丢失句柄和直接身份输出检测；
- 可选本地恢复审计模型。模型只能报告问题，不能修改绑定表；
- 交易动作恢复与资产、方向、数量、价格、权重合法性校验；
- NLPCC、StockBench、FinVault 共用的 Agent 生命周期适配接口；
- 本地 Qwen3.8-27B、企业 DeepSeek V4 Flash、GLM-5.1 的 OpenAI-compatible 配置；
- 49 项离线测试，不需要模型服务器和 API 即可运行。

目前已完成 `NLPCC 2026 Track 1 public A-set × Qwen3.8-27B` 的 2025 全年重放，公开的聚合结果见 [`benchmarks/results/nlpcc_real_2025_qwen38_p3.md`](benchmarks/results/nlpcc_real_2025_qwen38_p3.md)。这不是官方榜单提交；三基座、三 benchmark 的完整矩阵以及主动隐私攻击仍待运行。逐日匿名输出、本地恢复 action 和映射 ground truth 不提交，只保留在实验服务器。

## 4. 五分钟运行离线演示

要求 Python 3.8 或更高版本。

```bash
git clone git@github.com:lll-hhh/FinScope.git
cd FinScope
python3 -m pip install -e .
python3 examples/privacy_agent_demo.py
python3 -m unittest discover -s tests -v
```

最小代码：

```python
from finscope import LocalPrivacyAgent

catalog = [{
    "canonical_id": "600519.SH",
    "name": "贵州茅台",
    "aliases": ["600519"],
    "asset_type": "股票",
    "market": "A股",
    "sector_l1": "消费",
    "sector_l2": "食品饮料",
    "sector_l3": "白酒",
    "size_bucket": "大盘",
}]

privacy_agent = LocalPrivacyAgent(catalog, default_level="P3")
scope = privacy_agent.open_scope(
    "rebalance-001",
    "2026-08-21",
    conversation_id="research-risk-trading",
)

safe_prompt = privacy_agent.sanitize(
    "分析贵州茅台并给出目标仓位",
    scope,
    disclosure_level="P2",
    purpose="research",
)
external_output = external_llm(safe_prompt)
restored = privacy_agent.restore_and_audit(external_output, scope)

if restored.safe:
    print(restored.value)

# 最终交易必须使用严格入口；有任何歧义都会抛出异常，不会猜测。
validated = privacy_agent.validate_action(anonymous_action, scope)
mock_executor.execute(validated.action)
privacy_agent.close_scope(scope)
```

研究 Agent、风险 Agent 和交易 Agent 必须共享同一个 `scope`。工具调用的正确顺序是：匿名输出 -> 本地恢复真实工具参数 -> 本地查询 -> 再匿名工具结果 -> 外部模型。不要让真实工具参数或本地映射进入云端日志。

## 5. 模型怎么配置

计划比较三种金融决策基座：

| 名称 | 部署 | 配置用途 |
| --- | --- | --- |
| Qwen3.8-27B | 本地 vLLM/SGLang/OpenAI-compatible 服务 | 本地主实验基座，也可承担本地隐私规划/审计 |
| DeepSeek V4 Flash | 企业 OpenAI-compatible 网关 | 外部基座对照 |
| GLM-5.1 | 企业 OpenAI-compatible 网关 | 外部基座对照 |

官方公开模型 ID 可写为 `Qwen/Qwen3.8-27B`、`deepseek-v4-flash` 和 `glm-5.1`。但企业网关可能使用内部别名，因此 `EFUNDS_DEEPSEEK_MODEL` 与 `EFUNDS_GLM_MODEL` 必须按网关 `/models` 返回值或管理员说明填写，代码不会擅自猜测。

安装 provider 支持并配置：

```bash
python3 -m pip install -e '.[providers]'
cp .env.example .env
# 在 shell/密钥管理器中导出变量；本项目不会自动上传或打印密钥。
set -a
source .env
set +a
```

本地 Qwen 示例：

```bash
vllm serve Qwen/Qwen3.8-27B \
  --served-model-name Qwen/Qwen3.8-27B \
  --host 127.0.0.1 \
  --port 8000 \
  --tensor-parallel-size <按服务器GPU数量填写>

python3 examples/provider_demo.py
```

Python 中加载三套模型：

```python
from finscope import OpenAICompatibleChatModel, experiment_profiles

models = {
    name: OpenAICompatibleChatModel(profile)
    for name, profile in experiment_profiles().items()
}
answer = models["deepseek"].chat([
    {"role": "system", "content": "你是金融研究 Agent。"},
    {"role": "user", "content": anonymous_prompt},
])
```

把本地 Qwen 同时接成残余识别、P1-P5 planner 和恢复 auditor 的完整示例见 `examples/full_privacy_agent_config.py`。三个角色共用一个 endpoint，但各自使用受约束 JSON 协议和独立代码校验；真实映射仍只由 `FinScopeMediator` 管理。

安全要求：不要在 Python、README、提交记录、实验日志或聊天截图中保存真实 API key、用户名、账户 Token 和映射表。若密钥曾粘贴到公开或半公开对话中，应先在平台撤销并重新生成，再运行实验。

## 6. 三个主 Benchmark 怎么用

这些 benchmark 都带自己的任务循环或执行环境，不需要人为再造一个统一“金融 Agent”。FinScope 只统一它们与模型、工具、执行器之间的隐私钩子；每个 benchmark 原有的输入、策略和评分保持不变。

| Benchmark | 它本来测什么 | FinScope 接在哪里 | 原有特有指标 |
| --- | --- | --- | --- |
| NLPCC 2026 Shared Task 4 | 每日 Top-20 财经新闻 + 历史行情，输出 ETF 目标权重并日频回测 | 新闻/行情外发、权重输出和回测执行前 | Sharpe（主）、累计收益、最大回撤、权重格式/约束 |
| StockBench | 多月连续个股交易；Agent 根据价格、基本面和新闻做买/卖/持有 | 每日市场观察、分析链、交易 action 和组合状态 | 累计收益、最大回撤、Sortino、交易/任务完成情况 |
| FinVault | 31 个金融沙箱中的工具调用与执行安全，含正常任务和攻击任务 | 每个工具请求/返回、状态变化和最终执行 | 正常任务成功率、攻击成功率/防御率、违规执行率、过度拒绝率 |

NLPCC 的公开数据不是一个固定大模型 Agent，而是数据、DataLoader、starter kit、输出协议和回测器；参赛代码本身就是 Agent。它适合测试“新闻与行情 -> ETF 权重 -> 连续回测”的金融决策能力，但不会自动给出隐私攻击标签。FinScope 要额外保存仅本地可见的真实映射 ground truth，并构造重识别和跨日攻击。

统一接入方式：

```python
from finscope import (
    BenchmarkName, BenchmarkPrivacyAdapter, EpisodeContext,
    LocalPrivacyAgent, PrivacyRunConfig,
)

adapter = BenchmarkPrivacyAdapter(
    privacy_agent,
    PrivacyRunConfig(
        method="finscope",
        disclosure_level="P3",
        purpose="research",
    ),
)
adapter.open_episode(EpisodeContext(
    BenchmarkName.NLPCC_2026_TASK4,
    episode_id="20250102-track1",
    trading_day="2025-01-02",
    conversation_id="research-risk-trading",
))

safe_input = adapter.sanitize_llm_input(raw_agent_input, "20250102-track1")
anonymous_output = financial_model(safe_input)
restored = adapter.restore_llm_output(anonymous_output, "20250102-track1")
validated = adapter.validate_action(restored_action, "20250102-track1")
trace = adapter.close_episode("20250102-track1")
```

上游资料：

- [NLPCC 2026 Shared Task 4](https://github.com/splash-li/NLPCC2026-Shared-Task-4/tree/main/NLPCC_tasks/dataset)
- [StockBench](https://github.com/ChenYXxxx/stockbench)
- [FinVault](https://github.com/aifinlab/FinVault)

## 7. 五种主对比方法

三套 benchmark 都使用相同五组，实体识别结果和原始 Agent 配置保持一致，避免某组因为用了更强识别器而占便宜。

| 方法 | 说明 | 研究问题 |
| --- | --- | --- |
| Vanilla | 原始 Agent，无保护 | 效用上界和泄露上界 |
| Direct Deletion | 删除检测到的敏感实体/字段 | 删除会损失多少金融语义和执行能力 |
| LLM Rewrite | 让模型对敏感内容改写/泛化 | 自由改写是否造成事实漂移和不可恢复 |
| Episode Fixed Alias | episode 内固定纯代号，不做 P1-P5 与恢复审计 | 固定代号是否能完成任务、是否造成长期关联 |
| FinScope | P1-P5 双表示、作用域轮换、本地恢复与审计 | 是否兼顾隐私、语义、连续性和成本 |

`BenchmarkPrivacyAdapter` 已实现 `vanilla`、`deletion`、`fixed-alias` 和 `finscope` 的统一入口。`llm-rewrite` 会返回 `rewrite_required` 标记，实验 runner 必须显式调用同一指定改写模型；这样不会把一个没有实际调用改写模型的占位结果误当成基线。

## 8. 所有需要报告的共用指标

### 隐私

| 指标 | 怎么算 | 趋势 |
| --- | --- | --- |
| Direct Leak Rate | 外发 trace 中出现真实资产/账户/组合的比例 | 越低越好 |
| Asset ReID@1 / @5 | 攻击者猜中真实资产 Top-1/Top-5 的比例 | 越低越好 |
| Candidate Pool Recovery F1 | 推断候选池与真实候选池的集合 F1 | 越低越好 |
| Holding Inference F1 | 推断持仓资产集合的 F1 | 越低越好 |
| Weight MAE | 攻击者推断权重与真实权重的平均绝对误差 | 越高代表更难推断；需和 F1 一起报 |
| Cross-Day Link AUC | 判断两个跨日句柄是否属于同一资产的 AUC | 越接近 0.5 越好 |
| Action/Intent Accuracy | 攻击者推断买卖方向和调仓意图的准确率 | 越低越好 |
| Cumulative Leakage Curve | 随轮数/重试次数增加的 ReID、持仓恢复曲线 | 增长越慢越好 |

不要一开始只报告一个自定义 FAL 总分。先报告上述子指标、攻击候选池规模、随机基线、攻击模型、置信区间；只有确定权重和先验后再汇总 FAL。

### 恢复与流程连续性（B1 的主指标）

| 指标 | 定义 | 趋势 |
| --- | --- | --- |
| Exact Restoration Rate | 资产、动作、关系和结构完整恢复比例 | 越高越好 |
| Structured Action Exact Match | 恢复后 JSON action 与 Vanilla action 完全一致率 | 越高越好 |
| Tool Argument Recovery Success | 工具名和参数可被本地真实工具接受的比例 | 越高越好 |
| Weight MAE / Constraint Violation | 恢复权重误差及和不为 1、越界等比例 | 越低越好 |
| Execution Success Rate | 恢复后进入 mock/backtest 并成功执行的比例 | 越高越好 |
| Multi-round Task Completion | 整个多 Agent、多工具任务完成比例 | 越高越好 |
| Workflow Interruption / Retry Rate | 因歧义、格式和句柄错误中断或重试比例 | 越低越好 |
| State Equivalence | Vanilla 与防护版执行后的投资组合状态是否一致 | 越高越好 |
| Unsafe Repair Rate | 系统错误猜测并执行的比例 | 必须接近 0；FinScope 默认 fail-closed |

### 运行成本

- 外部输入/输出 Token、外部模型调用次数、重试次数；
- 本地识别、P1-P5 规划和恢复审计的调用次数；
- `recognizer_calls/skips/probes/new_replacements`，以及调用节省率；
- 本地阶段、外部阶段和端到端 p50/p95 延迟；
- 每任务和每交易日成本；
- 峰值显存、吞吐量和失败率。

## 9. 必须完成的实验矩阵

### E1 主实验：3 Bench × 5 方法 × 3 基座

对 NLPCC、StockBench、FinVault 分别运行 Vanilla、Deletion、LLM Rewrite、Episode Fixed Alias、FinScope；金融模型分别使用 Qwen3.8-27B、DeepSeek V4 Flash、GLM-5.1。固定 prompt、temperature、数据切分、Agent 工具、随机种子和预算。至少 3 个独立种子；连续交易任务还要报告不同市场时间窗，而不是只跑最好的一段。

输出三张主表：金融/正常任务效用表、隐私攻击表、恢复连续性与成本表。不同 benchmark 的原生分数不能硬平均；共用指标可以按 benchmark 分组报告。

### E2 五级披露实验：P1-P5

只对 FinScope 分别跑 P1、P2、P3、P4、P5，绘制：

- 披露等级 vs Asset ReID / Cross-Day Link；
- 披露等级 vs 原生金融指标和任务完成率；
- 披露等级 vs 恢复成功、重试和时延；
- 每级描述的 k-anonymity/候选集大小、唯一描述比例和平均信息字段数。

这组结果用来回答“白酒股票比纯代号多泄露了多少、又保留了多少效用”，也是以后训练或标定 Adaptive 策略的数据。

### E3 自适应策略

先用开发集拟合 `purpose -> 最低可用披露级别`，例如研究阶段 P2、风险阶段 P3、执行阶段 P5；约束条件是恢复/任务完成不低于设定阈值，目标最小化泄露和成本。把标定结果写入 `EmpiricalDisclosurePolicy`，只能在未参与标定的测试集报告结果。对比固定 P1-P5 和 Adaptive，禁止在测试集上挑级别。

### E4 恢复鲁棒性与故障注入（B1 核心）

对模型匿名输出自动注入：

- 句柄前后增加中英文前缀、后缀、引号、括号和所有格；
- 删除句柄但保留“该股/白酒股票”；
- 交换两个同类资产句柄；
- 复制、截断、大小写改变或编造旧句柄；
- 把数值字符串改成文本、权重和不为 1、数量越界；
- 多轮中将“它/该股/上述标的”指向错误对象；
- 工具返回结构变更、模型重试和部分 JSON；
- 上一交易日句柄重放到新交易日。

报告 Exact Restoration、State Equivalence、拒绝/重试率和 Unsafe Repair。任何歧义宁可拒绝，不得为了提高成功率静默猜测。

### E5 隐私攻击

统一攻击者可观察所有外发 prompt/output、跨 Agent trace 和跨日 trace，并可使用公开新闻行情。至少包括：

- 直接询问和提示注入索要真实资产/映射；
- 新闻文本、行业、价格轨迹的资产重识别；
- 候选池和持仓恢复；
- 调仓动作/意图推断；
- 跨 Agent trace 聚合；
- 跨日成对关联与整条轨迹聚类；
- 重试次数 1/3/5/10 下的累计泄露；
- 候选池规模 20/100/500/全资产池的敏感性分析；
- 主动查询、格式、频率和时延侧信道。

攻击模型不能看到本地映射 ground truth；ground truth 只由离线评分器读取。报告随机基线和至少一种强攻击模型。

### E6 Privacy Agent 消融

- 只有规则/security master；
- 规则 + 本地残余识别；
- 再加 P1-P5 planner；
- 再加确定性恢复审计；
- 完整系统 + 本地语义 auditor；
- 去掉事实校验，让模型描述直接生效；
- 去掉句柄，仅保留“白酒股票”等描述；
- 去掉 scope 轮换或改成全局固定句柄；
- always scan vs gated scan；
- 无 cache vs cache；
- 无代词复用 vs 有代词复用。

这组实验用于证明贡献来自“可验证的隐私 Agent 和恢复机制”，而不是普通字符串替换。

### E7 模型和成本实验

- 三个 27B/云端基座的金融效用、泄露和格式遵循差异；
- 隐私规划/审计使用规则、0.6B 级小模型和 Qwen3.8-27B 的准确率/漏检/时延对比；
- 连续无新实体时门控节省多少调用，风险信号后能否重新唤醒；
- 冷启动、缓存命中和周期 probe 的 p50/p95；
- 如果 0.6B 漏检过高，再逐级增大模型，不能只因“小”而选它。

## 10. A1 与 B1 的论文边界

A1 可以主讲“识别和替换什么、哪种匿名化降低了多少泄露”。B1 不应把贡献只写成另一种替换算法，而应主讲：

1. 一个本地 Privacy Agent 如何创建**可验证、带生命周期的语义绑定**；
2. 外部匿名推理之后如何完成**类型化恢复、工具参数恢复和状态等价执行**；
3. 句柄丢失、同类资产、代词、多轮重试和旧句柄重放时如何检测歧义并安全失败；
4. 识别/规划/审计模型如何通过缓存和门控控制在线时延；
5. 用恢复成功率、流程中断率、状态等价和 Unsafe Repair 等 B1 专属指标证明系统价值。

可以把方法称为 **Local Privacy Mediation Agent**：小模型提出敏感项和分级描述，安全主表验证，本地绑定器发放句柄，代码恢复器恢复，语义审计器检查。论文中不要说“模型负责恢复真实资产”，真实恢复权必须始终在本地确定性代码中。

## 11. 目录与交接

```text
finscope/core.py          基础识别、映射、生命周期、恢复、动作校验
finscope/policy.py        动态风险等级和残余扫描门控
finscope/recognizer.py    本地模型实体识别与输出校验
finscope/privacy_agent.py P1-P5 规划、语义绑定、恢复审计
finscope/providers.py     三类 OpenAI-compatible 模型配置
finscope/benchmarks.py    三套 benchmark 的统一隐私钩子
examples/                 离线和 provider 示例
tests/                    回归测试
docs/                     背景、快速入门和服务器交接提示词
```

新服务器上的 Agent 请先阅读：

- [完整项目背景](docs/project_background.md)
- [基础实现说明](docs/finscope_quickstart.md)
- [COLING 故事、实验清单与表格](docs/coling_story_experiment_tables.md)
- [StockBench/FinVault 接入与 Qwen 全量调度](docs/external_benchmark_integration.md)
- [服务器交接启动提示词](docs/agent_handoff_prompt.md)

## 12. 安全与复现底线

- `.env`、API key、账户 Header、真实持仓和真实映射永不提交；
- 云端 trace 只保存匿名内容和不可逆 trace id；
- ground truth 与云端 trace 分目录、分权限保存；
- 所有实验记录 Git commit、模型实际 ID、数据 hash、prompt 版本、随机种子和失败案例；
- NLPCC 新闻数据仅按其许可用于学术评测；
- 真实交易 API 不得接入本实验，统一使用回测、mock 或 paper-trading；
- 测试通过只说明软件行为符合预期，不代表已经获得隐私或收益实验结论。
