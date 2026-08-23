# FinScope：问题定义、论文故事与相关工作定位

更新日期：2026-08-22。本文用于确定 B1 的 COLING 论文定位。相关工作结论基于截至该日期可检索到的论文；其中 2026 年的 MNC、OCELOT、SecureClaw、PromptGraph 和 FinHarness 目前应按 arXiv 预印本表述，不应写成已经同行评审的结论。

## 1. 建议定位

### 暂定标题

**FinScope: A Local Agent for Semantic Assurance under Privacy Constraints in Financial Multi-Agent Systems**

中文：**FinScope：金融多智能体系统中隐私约束下的本地语义保障智能体**

这里不把 FinScope 写成“隐私中间层”，也不把去标识化或 P1-P5 披露策略作为 B1 的贡献。它们属于 A1 或双方共享的受保护输入接口。FinScope 是金融多智能体系统中新增的本地智能体；隐私是它必须满足的约束，跨 Agent 指称状态、身份恢复和安全执行是 B1 要解决的主要问题。

### 一句话问题

金融多智能体可以在不向外部模型暴露真实金融实体身份的情况下完成推理吗？更重要的是，模型生成的受保护结果能否在本地被无歧义地恢复为正确、合法、可执行的工具参数和交易动作？

### 一句话方法

FinScope 在本地把金融实体绑定为“任务所需的受验证语义描述 + 作用域内唯一句柄”，让外部模型基于描述推理、基于句柄指称对象，再由本地智能体确定性恢复句柄、审计歧义并在执行前进行 fail-closed 校验。

## 2. 背景

金融语言智能体已经从单轮问答转向由研究、风险、交易和工具节点组成的连续工作流。一个交易任务会跨越新闻检索、行情读取、候选池分析、组合状态更新和订单执行。外部大模型因此不仅看到自然语言，还可能看到资产代码、候选池、持仓、权重、调仓方向以及跨日轨迹。单条信息看似无害，多轮、多 Agent 和公开行情结合后仍可能暴露资产身份或投资意图。

现有输入保护通常采用删除、替换、泛化、重写或加密。它们可以降低直接泄露，却没有自动解决金融工作流的另一半问题：研究 Agent、风险 Agent 和交易 Agent 必须持续确认自己讨论的是同一资产，模型输出还必须回到真实证券代码、工具参数和交易动作。删除会破坏任务语义；纯随机代号会使模型缺少决策信息；自由改写可能产生事实漂移；长期固定代号又会形成跨日关联标识。

在普通聊天中，恢复错误可能只是显示错误；在金融 Agent 中，错误恢复会改变被查询或交易的资产。因此，恢复不是界面后处理，而是执行安全的一部分。系统既要让外部模型获得足够但不过量的金融语义，又要保证返回的实体指称在本地唯一、可验证、可恢复，且损坏、伪造、过期或歧义结果不会进入执行器。

A1 可以研究敏感信息如何识别、隐藏以及抵抗重识别攻击。B1 研究的是另一个运行时问题：经过保护的信息如何继续支撑多 Agent 推理，并被可靠地恢复为可执行的金融状态。两者共享隐私攻击和匿名化基线，但 B1 的结论必须由恢复正确性、流程连续性、交易执行和运行成本共同支撑。

## 3. 问题定义

### 3.1 系统与信任边界

考虑一个由研究、风险、交易和工具节点组成的金融多智能体工作流。外部任务模型负责语言推理和动作生成；FinScope、证券主表、作用域映射、组合状态和最终执行器位于可信本地域。外部模型服务及其日志被视为 honest-but-curious，并可能受到提示注入、主动探测或累计查询攻击。

本阶段不防御本地主机、证券主表或执行器已经被攻破的情况，也不声称语义描述具有密码学匿名保证。即使原始名称完全移除，行业、市场、规模、新闻和价格组合仍可能支持统计重识别，因此隐私强度必须通过 ReID 和跨作用域关联攻击测量，而不能由“字符串中没有真实名称”推断。

### 3.2 双表示与恢复

对作用域 `s = (task, conversation, trading_day)` 中的敏感金融实体 `e`，FinScope 生成：

```text
z_s(e, level) = <fin-ref id=h_s(e)> d_level(e) </fin-ref>
```

- `h_s(e)` 是作用域内唯一的类型化句柄，只承担稳定指称和本地恢复；
- `d_level(e)` 是 P1-P5 中一个由证券主表验证的金融语义描述，只提供当前任务需要的信息；
- 同一作用域内的多个 Agent 共享绑定，不同任务、会话或交易日重新生成绑定；
- 外部模型输出中的句柄由本地映射确定性恢复，随后对资产、动作、数量、权重和业务状态进行验证。

若句柄未知、过期、缺失、发生类型冲突，或同一输出存在多种合法恢复，系统必须拒绝执行，而不是猜测一个真实实体。

### 3.3 优化目标

FinScope 不是只优化一个隐私分数，而是同时考察四类目标：

1. **披露约束：** 降低真实资产重识别和跨作用域关联，同时记录直接泄露与累计泄露。
2. **语义保真：** 保留金融决策所需信息，使 Benchmark 原生任务指标尽量接近未保护的 Agent。
3. **恢复与执行：** 最大化 Exact Restore、工具参数恢复和真实执行成功率，最小化 Unsafe Repair。
4. **运行成本：** 控制额外 token、模型调用、重试和端到端尾延迟。

这四项目标存在真实冲突。更粗的 P5 描述通常降低身份推断，但也可能降低金融效用；更细的 P1/P2 描述提高任务信息量，也增加重识别风险。论文应报告这条前沿，而不是声称存在无代价的完全匿名。

### 3.4 研究问题

- **RQ1：** P1-P5 不同金融语义粒度如何影响原生任务效用与资产重识别？
- **RQ2：** 作用域内稳定、作用域外轮换的绑定能否兼顾多 Agent 指称连续性和跨日不可关联性？
- **RQ3：** 外部模型输出能否被准确恢复为真实工具参数和金融动作；在句柄损坏、伪造、交换、过期和歧义时能否正确拒绝？
- **RQ4：** 上述能力在 NLPCC、StockBench 和 FinVault 的连续工作流中带来多少 token、时延、重试和任务效用开销？

## 4. 创新点

以下贡献应写成 FinScope 的金融运行时闭环，不应把 A1 的去标识化/P1-P5，或已有的替换、句柄和输出恢复单独声称为 B1 创新。

### 4.1 可恢复的金融语义契约

B1 接收 A1 或共享保护模块产生的 P1-P5 金融描述，不把描述生成本身作为贡献。FinScope 为这些描述附加类型、canonical entity、scope 和允许执行边界，形成可由研究、风险、交易和工具节点共同使用的恢复契约。证券主表在 B1 中用于验证绑定和恢复结果，而不是重新定义匿名化策略。

### 4.2 面向多 Agent 工作流的生命周期绑定

绑定状态由独立的本地 Agent 管理，并由研究、风险和交易节点在同一任务中共享。其生命周期与任务、会话和交易日对齐，使任务内指称稳定，任务外标识轮换。这里的重点不是“有 TTL”，而是这种生命周期如何影响连续金融决策、跨日链接和工具调用。

### 4.3 把恢复错误作为执行安全问题

FinScope 将恢复分为确定性句柄解析、歧义审计和业务动作校验。它不仅报告恢复成功率，还通过故障注入测量系统对损坏、伪造、过期、类型冲突和句柄交换的正确拒绝率及 Unsafe Repair。恢复失败不能静默退化为另一个合法资产或动作。

### 4.4 隐私、金融效用与可执行连续性的联合评测

论文在相同任务轨迹上同时报告 Benchmark 原生指标、主动重识别与跨日关联、Exact Restore/Unsafe Repair，以及 token 和 p95 时延。其研究对象不是静态匿名文本，而是“保护后的语言结果能否安全回到金融环境状态”的完整闭环。

## 5. 故事主线

### 5.1 开场：隐私保护后的 Agent 还能不能行动

金融多智能体依赖外部大模型理解新闻和市场，但原始上下文会暴露资产、持仓与策略。已有工作已经说明可以删除、改写、假名化或限制披露；真正未解决的金融问题是：保护后的语言表示如何跨研究、风控、工具和交易节点保持同一对象，并最终恢复成正确动作。

### 5.2 三类失败

1. **原始输入可执行但暴露。** Vanilla 保留全部任务信息，也给外部模型和日志完整的身份与轨迹。
2. **删除或自由改写降低暴露但破坏闭环。** 模型可能无法选择资产，或生成无法映射回证券主表的文本。
3. **固定假名保持引用但缺少边界。** 纯代号缺少金融语义；全局代号可被长期关联；即使代号可恢复，损坏或被替换的句柄仍可能导致错误执行。

### 5.3 FinScope 的回答

FinScope 作为额外的本地智能体参与工作流：在请求发出前，它选择并验证任务所需的金融语义，签发唯一句柄并维护生命周期；在结果返回后，它恢复真实实体，审计指称和结构，并只把通过业务约束的动作交给执行器。外部模型负责金融推理，本地 Agent 掌握真实映射和执行权限，两者职责分离。

### 5.4 证据链

论文结论应按以下顺序建立：

1. P1-P5 确实形成可测量的隐私—效用前沿；
2. 句柄让语义相近的多个资产仍可唯一恢复；
3. 作用域轮换降低跨日关联，同时不破坏任务内多 Agent 协作；
4. FinScope 的恢复结果与本地 ground truth 一致，异常结果能够 fail-closed；
5. 上述性质在连续金融 Benchmark 中保留可接受的原生效用，并具有可量化的运行开销。

收益率高于 Vanilla 不能作为核心结论，它可能来自模型随机性。核心结论应是相对于 Vanilla 的任务效用保持、相对于匿名化基线的恢复与执行连续性，以及相对于固定代号的跨作用域关联下降。

## 6. 建议贡献表述

论文可以使用以下四点贡献，不使用未经证实的“首个”：

1. **Problem formulation.** We formulate privacy-constrained semantic assurance for financial multi-agent workflows, where protected language outputs must be restored into correct and executable financial actions rather than merely remain readable.
2. **Local agent.** We develop FinScope, a local agent that turns protected financial descriptions into lifecycle-scoped recoverable bindings shared across research, risk, trading, and tool interactions.
3. **Audited restoration.** We make restoration a first-class safety boundary through deterministic binding, ambiguity auditing, state-aware action validation, and fail-closed handling of malformed, stale, forged, and out-of-scope references.
4. **Evaluation.** We evaluate financial utility, active re-identification and linkage, restoration safety, execution continuity, and online cost under one protocol across three financial-agent benchmarks and multiple base models.

## 7. 当前实证证据

本节保留的数字来自旧版 deterministic local-agent，虽然可以由历史 artifact 复核，但不符合当前“Qwen3.8-27B 任务模型 + ≤4B 本地隐私 Agent”的正式协议。它们只作工程参考，不能写入最终主表或摘要；新的严格单元必须等待 v6 重跑完成。数据来自 NLPCC 2026 Track 1 public A-set，**不是 NLPCC 官方榜单成绩**。

### 7.1 六方法主结果（旧版工程参考，不是最终结果）

前四列是 NLPCC 原生金融任务指标，后六列是 FinScope 协议补充的隐私、恢复安全与系统成本指标。隐私主攻击者是 `public-side-information oracle`：它使用公开证券主表属性和价格侧信息，但看不到本地句柄、持仓或映射；它不是 Qwen 任务模型本身。

| Method | Sharpe ↑ | Return ↑ | MDD ↓ | Valid ↑ | ReID@1 ↓ | Link AUC →.5 | Exact Restore ↑ | Unsafe Repair ↓ | Token Δ ↓ | E2E p95 ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 2.426 | 39.45% | 6.88% | 99.18% | 100.00% | 1.000 | -- | -- | ref. | 8.216 s |
| Deletion | 0.000 | 0.00% | 0.00% | 0.00% | 100.00% | 1.000 | -- | -- | -3.4% | 7.751 s |
| LLM Rewrite | 2.165 | 36.30% | 6.86% | 100.00% | 100.00% | 1.000 | -- | -- | +10.6% | 27.663 s |
| Global Alias | 2.264 | 25.28% | 4.43% | 97.53% | 100.00% | 1.000 | 100.00% | 0.00% | +0.1% | 8.180 s |
| Episode Alias | 2.260 | 33.14% | 6.29% | 99.59% | 100.00% | 1.000 | 100.00% | 0.00% | +3.6% | 8.364 s |
| **FinScope P3** | **2.976** | 34.31% | **3.34%** | **100.00%** | **53.20%** | **0.789** | **100.00%** | **0.00%** | **-50.9%** | **7.031 s** |

`--` 表示方法没有身份恢复阶段，指标不适用。Deletion 的 MDD 为零是因为没有任何交易成功执行，不能解读为风险控制优势。FinScope P3 相对 Vanilla 保留 87.0% 累计收益，并将 ReID@1 从 100% 降至 53.20%，但 53.20% 仍显著高于 11 选 1 的 9.09% 随机基线，因此当前证据只支持“降低重识别风险”，不支持“完全匿名”。收益和 Sharpe 高于 Vanilla 也不能单独作为方法贡献，因为不同提示表示可能改变模型决策轨迹。

### 7.2 P1-P5 隐私—效用前沿

| Level | 语义粒度 | Sharpe ↑ | ReID@1 ↓ | Link AUC →.5 |
| --- | --- | ---: | ---: | ---: |
| P1 | 最丰富的受验证语义 | 2.047 | 93.27% | 0.872 |
| P2 | 较丰富语义 | 1.934 | 88.10% | 0.871 |
| P3 | 标准语义 | **2.976** | 53.20% | 0.789 |
| P4 | 粗粒度语义 | 1.434 | 24.24% | 0.647 |
| P5 | 最小语义/执行句柄 | 1.856 | **9.09%** | **0.500** |

从 P1 到 P5，重识别和跨日关联能力整体下降，P5 达到本实验的随机基线；与此同时金融效用并不单调，P3 在当前运行中形成更合适的经验折中。P3 不能因为单次 Sharpe 最高而在测试集上事后选定，最终论文应通过开发集确定默认级别或自适应策略，再在测试集冻结评测。

### 7.3 恢复、执行与故障注入

FinScope P3 的自然运行执行成功率为 99.2%（241/243）；干净输出的 Exact Restore 为 100%（243/243）。在 P1-P5 自然运行汇总中，系统记录了 6 次 malformed JSON、3 次 `direct_identity_output` 审计拒绝和 1 次卖出空持仓，均应作为流程诊断保留。

| Perturbation | Cases | Exact Restore ↑ | Correct Reject ↑ | Unsafe Repair ↓ |
| --- | ---: | ---: | ---: | ---: |
| Prefix/suffix/quotes/brackets | 243 | 100.0% | -- | 0.0% |
| Descriptor without handle | 243 | 0.0% | 100.0% | 0.0% |
| Binding descriptor tamper | 243 | 0.0% | 100.0% | 0.0% |
| Truncated handle | 243 | 0.0% | 100.0% | 0.0% |
| Fabricated handle | 243 | 0.0% | 100.0% | 0.0% |
| **Swap two same-type handles** | **243** | **0.0%** | **0.0%** | **100.0%** |
| Malformed JSON | 243 | 0.0% | 100.0% | 0.0% |
| Out-of-range amount/weight | 243 | 0.0% | 100.0% | 0.0% |
| Cash/state violation | 243 | 0.0% | 100.0% | 0.0% |
| Stale previous-day handle | 242 | 0.0% | 100.0% | 0.0% |

因此主表中的 Unsafe Repair 0% 只针对损坏、伪造、过期、缺失和业务越界等应拒绝集合。**同类型、格式完整且在当前 scope 内合法的句柄互换仍会通过解析，Unsafe Repair 为 100%**；这是当前实现无法仅凭句柄真实性识别“意图替换”的明确安全边界，必须单独披露，不能被聚合值隐藏。

### 7.4 当前完成范围

| Benchmark x Base LM 单元 | 状态 | 当前可报告结果 |
| --- | --- | --- |
| NLPCC x Qwen3.8-27B | **旧版 preliminary** | deterministic local-agent 结果仅用于工程回归；严格 ≤4B 本地 Agent 正式单元待重跑 |
| StockBench x Qwen3.8-27B | **重跑中断，待重启** | 旧 Vanilla 与 502 期间中间产物均不进入正式结果 |
| 其余 StockBench/FinVault 与其他基座模型 | 未形成最终单元 | 不写入正式比较结论 |

当前没有一个符合新协议的 Benchmark x Base LM 完整单元可作为最终主表结果。旧版 NLPCC 只能证明工程闭环曾经运行，不足以支持隐私 Agent 的论文结论；StockBench 的 502 中间值和 FinVault 中间值均不得当作最终结果或填入论文主表。

完整逐日记录、置信区间、成本诊断和大主表见 [`coling_story_experiment_tables.md`](coling_story_experiment_tables.md)，正式机器可读结果位于 `benchmarks/results/*_final.json`。

## 8. 相关工作

### 8.1 文本匿名化与隐私—效用权衡

HaS 最早一批明确研究“隐藏后再找回”的 LLM prompt 框架：先替换私有实体，再用本地小模型对 LLM 结果去匿名化。Casper 和 Portcullis 也分别实现了本地占位符映射与响应重建。它们与 FinScope 的本地恢复机制直接相关，因此“本地替换并恢复 LLM 输出”不能作为 FinScope 的独立首创点。FinScope 的差异应落在证券事实约束的金融绑定、跨 Agent/跨日生命周期、确定性恢复安全和真实金融动作闭环。

PAPILLON 将本地模型与远程模型组合为 Privacy-Conscious Delegation，在保留回答质量的同时减少 PII 泄露。它直接支持“任务相关的最小必要信息”动机，但主要优化 prompt 或回答质量，没有把金融实体恢复和执行状态转换作为主要评测对象。

PromptGraph 是尤其接近的 2026 年预印本：它显式建模 span 隐私和上下文依赖，在本地清洗，并在一致性检查后恢复占位符。因此 FinScope 不能把“语义敏感清洗 + 本地一致性恢复”写成新颖性本身；必须以金融多 Agent 生命周期、证券主表验证、恢复故障和执行连续性与其区分。

### 8.2 LLM Agent 的隐私与安全

PrivacyAsst 面向 tool-using LLM agents，使用同态加密和属性打乱保护发送给工具的用户输入，是需要正面对比的 Agent 隐私框架之一。MAGPIE 评估多 Agent 协作中的上下文隐私，Privacy-R1 学习本地与远程模型之间的隐私路由；它们不研究金融实体的确定性恢复。

OCELOT 将 Agent 隐私建模为跨轨迹的推断泄露预算，通过本地模型提出候选释放、确定性验证器审批，并考虑累计泄露。MNC 进一步提出 typed semantic declassification，并绑定 recipient、purpose、forwarding、lifetime、logging 和 memory scope。这两项工作与 FinScope 的任务相关披露和生命周期非常接近。因此，论文不应继续使用“Scope-Bound Semantic Privacy Mediation”作为标题，也不能笼统声称首次提出作用域化语义披露。

SecureClaw 是当前架构上最强的近邻：它在读取边界提供 opaque handle 和 bounded summary，在写入边界通过可信执行器执行 PREVIEW-to-COMMIT，并把 session、TTL 和允许解引用的 sink 绑定到句柄。它已经覆盖“句柄 + 摘要 + 可信执行器 + fail-closed”这条一般系统主线。FinScope 与它的可辩护差异不是组件名称，而是金融实体语义如何由证券主表约束、P1-P5 如何形成重识别—任务效用前沿、恢复错误如何改变金融状态，以及这些问题如何在连续金融 Benchmark 中联合测量。

RTBAS 聚焦提示注入、信息流和未授权工具调用，为 FinScope 的攻击与执行门控提供背景，但不研究经过身份保护的金融输出如何恢复为 canonical asset 和组合动作。

### 8.3 金融语言智能体

FinCon、FinRobot 和 TradingAgents 展示了多角色辩论、工具增强和连续交易在金融语言 Agent 中的用途，但它们主要优化金融决策能力，没有提供本地身份绑定和恢复安全机制。

FinHarness 是金融领域最直接的安全近邻。它使用 Query Monitor、Tool Monitor 和分级 LLM judge 对金融 Agent 的查询漂移与工具调用进行在线干预，并在 FinVault 上评测攻击成功率与正常任务批准率。FinScope 不能声称首次为金融 Agent 增加运行时安全组件；差异在于 FinHarness 判断请求和工具调用是否危险，而 FinScope 研究受保护金融实体如何保留语义、恢复身份并安全进入执行状态。

## 9. B1 直接相关性判断

上一节中的通用隐私工作用于检查组件是否已有先例，不能直接视为 B1 的同题工作。B1 的直接竞争工作必须同时满足三个硬条件：

1. 研究对象是**金融多智能体工作流**，而不是普通聊天、单 Agent 或静态文本；
2. 系统包含独立的本地保护角色或可信组件，并跨研究、风险、交易和工具节点维护状态；
3. 研究终点包含“保护表示 -> 外部推理 -> 本地身份/动作恢复 -> 金融执行”，而不只测输入匿名化或危险工具拦截。

### 9.1 按 B1 硬条件筛选

| 工作 | 金融 | 多智能体 | 本地保护角色 | 身份/语义保护 | 本地恢复 | 金融执行闭环 | 与 B1 的关系 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FinCon | 是 | 是 | 否 | 否 | 否 | 是 | 金融多 Agent 基座 |
| FinRobot | 是 | 是 | 否 | 否 | 否 | 部分 | 金融多 Agent 平台 |
| TradingAgents | 是 | 是 | 否 | 否 | 否 | 是 | 最接近的金融多 Agent 基座 |
| FinHarness | 是 | 非核心 | 是，安全 harness | 否 | 否 | 是 | 金融运行时安全近邻，不研究保护后恢复 |
| MAGPIE | 否 | 是 | 否，Benchmark | 是 | 否 | 否 | 多 Agent 隐私评测，不是金融系统 |
| Privacy-R1 | 否 | 是 | 是，路由 Agent | 是 | 否 | 否 | 多模型隐私协作，不做金融恢复 |
| MNC | 否 | 是 | 是，reference monitor | 是 | 非主要问题 | 否 | 多 Agent 作用域通信近邻 |
| SecureClaw | 否 | 非核心 | 是，可信组件组 | 是 | 是，sink 解引用 | 通用外部动作 | 最接近恢复执行机制，但不是金融多 Agent |
| FinScope | 是 | 是 | 是，本地 Agent | 是 | 是 | 是 | B1 |

按这三个条件，截至 2026-08-22，本次检索**没有发现与 B1 完全同题的工作**。现有文献分成两边：金融多智能体工作不研究身份保护与恢复；多 Agent 隐私和安全工作不研究金融实体恢复后的交易连续性。FinScope 的研究空间正是两者的交叉，而不是重新发明任意一边已有的单个组件。

### 9.2 金融多智能体中受保护信息的恢复与执行：相关工作研究版图

| 问题 / 方案 | 受保护表示与语义保留 | 跨 Agent 状态与生命周期 | 本地恢复与真实实体重绑定 | 工具、动作与执行保障 |
| --- | --- | --- | --- | --- |
| 可恢复 Prompt 保护 | 本地—远程协作与语义保留：PAPILLON [3]；上下文关系清洗：PromptGraph [5] | -- | 占位符/实体恢复：HaS [1]、Casper [2]、Portcullis [4]、PromptGraph [5] | -- |
| Tool-using Agent 隐私 | 加密或属性扰动：PrivacyAsst [6] | 跨轨迹泄露预算：OCELOT [9] | 句柄在可信 sink 解引用：SecureClaw [11] | 信息流和危险调用控制：PrivacyAsst [6]、SecureClaw [11]、RTBAS [12] |
| 通用多智能体隐私 | 多 Agent 隐私评测：MAGPIE [7]；隐私感知模型路由：Privacy-R1 [8]；最小必要语义披露：MNC [10] | 多轮协作评测：MAGPIE [7]；学习型路由状态：Privacy-R1 [8]；显式 recipient/purpose/lifetime scope：MNC [10] | -- | 通信转发、日志与记忆约束：MNC [10] |
| 金融多智能体决策 | -- | 多角色协作：FinCon [13]、FinRobot [14]、TradingAgents [15] | -- | 金融分析、工具与交易闭环：FinCon [13]、FinRobot [14]、TradingAgents [15] |
| 金融 Agent 运行时安全 | -- | 跨轮风险漂移：FinHarness [16] | -- | Query/Tool Monitor 与分级 judge：FinHarness [16] |
| **B1：FinScope（本文）** | **接收 A1/共享模块的 P1-P5 受保护金融描述，并验证其证券事实** | **独立本地 Agent 在研究—风险—交易—工具节点间维护任务/会话/交易日级绑定** | **确定性恢复 canonical entity、权重和动作；审计歧义、伪造、过期和句柄交换** | **恢复后状态校验、工具参数校验、交易前 fail-closed，并评测执行连续性** |

这张表表达的是研究交叉点，而不是声称 FinScope 的每个组件都是首次提出。现有文本隐私工作集中在第一列和第三列；通用 Agent 隐私工作集中在前两列或第四列；金融多智能体工作集中在第二列和第四列。当前没有一项既有工作同时覆盖 B1 所需的四列，并把第三列的恢复错误作为金融执行风险进行评测。

## 10. 新颖性审计

### 不能再声称的内容

- 不能声称首次在本地替换敏感实体并恢复 LLM 输出：HaS、Casper、Portcullis 和 PromptGraph 已覆盖。
- 不能声称首次使用任务相关语义而非纯删除来平衡隐私与效用：PAPILLON、MNC 和 PromptGraph 已覆盖相邻问题。
- 不能声称首次为 Agent 使用 opaque handle、生命周期或可信执行器：MNC 和 SecureClaw 已高度重合。
- 不能声称首次为金融 Agent 增加运行时安全监控：FinHarness 已在 FinVault 上做过在线安全 harness。
- 不建议继续使用 **Lifecycle-Bound/Scope-Bound Semantic Privacy Mediation** 作为标题或核心术语；它与 MNC 的标题和机制表述过近。

### 当前仍可辩护的 B1 空间

截至 2026-08-22，本次检索尚未发现一项工作同时完成以下闭环：

1. 用证券主表验证多级金融语义，而不是泛化 PII 占位符或固定摘要；
2. 在研究—风险—交易多个 Agent 间维持任务内唯一指称，并跨交易日轮换；
3. 将外部语言输出确定性恢复为 canonical financial entities、权重和动作；
4. 用恢复故障注入和真实执行状态测量 Exact Restore、Correct Reject 和 Unsafe Repair；
5. 在连续金融决策、交易和安全 Benchmark 上联合报告重识别、金融效用、恢复连续性与成本。

这支持一个“问题与评测闭环”的贡献，但不足以无条件声称基础机制首创。论文最稳妥的表述是 `we formulate`、`we operationalize`、`we develop` 和 `we evaluate`。只有在投稿前完成系统文献检索并确认没有遗漏时，才考虑带限定条件的 `to our knowledge`。

## 11. 编号参考文献（最相关的 16 篇）

[1] Chen et al. [Hide and Seek (HaS): A Lightweight Framework for Prompt Privacy Protection](https://arxiv.org/abs/2309.03057). arXiv, 2023.

[2] Chong et al. [Casper: Prompt Sanitization for Protecting User Privacy in Web-Based Large Language Models](https://arxiv.org/abs/2408.07004). arXiv, 2024.

[3] Li et al. [PAPILLON: Privacy Preservation from Internet-based and Local Language Model Ensembles](https://arxiv.org/abs/2410.17127). NAACL, 2025.

[4] Zhan et al. [Portcullis: A Scalable and Verifiable Privacy Gateway for Third-Party LLM Inference](https://doi.org/10.1609/aaai.v39i1.32088). AAAI, 2025.

[5] Gu et al. [PromptGraph: Graph-Guided Prompt Sanitization for Balancing Privacy and Utility in LLM Inference](https://arxiv.org/abs/2607.10709). arXiv preprint, 2026.

[6] Zhang et al. [PrivacyAsst: Safeguarding User Privacy in Tool-Using Large Language Model Agents](https://doi.org/10.1109/TDSC.2024.3372777). *IEEE TDSC*, 2024.

[7] Juneja et al. [MAGPIE: A Benchmark for Multi-Agent Contextual Privacy Evaluation](https://arxiv.org/abs/2510.15186). arXiv preprint, 2025.

[8] Hui et al. [Privacy-R1: Privacy-Aware Multi-LLM Agent Collaboration via Reinforcement Learning](https://doi.org/10.18653/v1/2026.acl-long.2130). ACL, 2026.

[9] Xie and Li. [OCELOT: Inference-Leakage Budgets for Privacy-Preserving LLM Agents](https://arxiv.org/abs/2606.12341). arXiv preprint, 2026.

[10] Xu et al. [MNC: Scope-Bound Semantic Declassification for Private LLM-Agent Communication](https://arxiv.org/abs/2608.01719). arXiv preprint, 2026.

[11] Ma and Schmid. [SecureClaw: Clawing Back Control of LLM Agents](https://arxiv.org/abs/2606.09549). arXiv preprint, 2026.

[12] Zhong et al. [RTBAS: Defending LLM Agents Against Prompt Injection and Privacy Leakage](https://arxiv.org/abs/2502.08966). arXiv preprint, 2025.

[13] Yu et al. [FinCon: A Synthesized LLM Multi-Agent System with Conceptual Verbal Reinforcement for Enhanced Financial Decision Making](https://arxiv.org/abs/2407.06567). NeurIPS, 2024.

[14] Yang et al. [FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models](https://arxiv.org/abs/2405.14767). arXiv, 2024.

[15] Xiao et al. [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138). arXiv, 2024.

[16] Jia et al. [FinHarness: An Inline Lifecycle Safety Harness for Finance LLM Agents](https://arxiv.org/abs/2605.27333). arXiv preprint, 2026.

## 12. 投稿前必须补的证据

1. 把 SecureClaw、PromptGraph、MNC、OCELOT、Portcullis 和 FinHarness 加入 Related Work，并在正文中主动承认重合组件。
2. 主实验保留 Deletion、LLM Rewrite、Global Alias 和 Episode Alias；如工程允许，至少增加一个“opaque handle + fixed bounded summary + deterministic restore”的 SecureClaw-style 强基线。
3. 恢复故障注入必须成为主结果或关键补充表，而不是只放实现说明；否则 B1 与通用 prompt anonymization 的差异不成立。
4. 报告恢复后的状态等价性和执行结果，不能用 JSON Valid 或句柄命中率代替 Exact Restore。
5. 对 P1-P5 描述报告证券事实错误率、候选集大小/唯一描述率和重识别结果，证明证券主表验证不是只增加了工程代码。
6. 清楚区分经验隐私和形式化保证：FinScope 当前可以证明映射留在本地、非法句柄拒绝等代码性质，但不能证明 P1-P5 描述不会被外部知识重识别。
