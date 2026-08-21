# FinScope 项目背景、B1 方案与实验蓝图

本文是 FinScope B1 方向的完整交接材料，记录项目背景、会议结论、问题定义、当前代码状态、模型分工、数据集接入方式、攻击评测和后续实现边界。文档状态：2026-08-21。它是研究和工程交接文档，不是投资建议。

## 1. 项目摘要

金融 Agent 会把新闻分析、行情摘要、候选资产池、持仓状态和交易意图发送给外部大模型。即使删除部分字段，外部模型仍可能通过公开新闻、价格、连续对话和多个 Agent 的交互记录恢复资产身份、候选池、持仓变化和长期策略；但如果把所有实体都删除，研究、风控、交易 Agent 又无法确认讨论的是同一资产，工具参数和交易执行会失败。

FinScope 是部署在金融 Agent 与外部大模型之间的本地隐私 Agent。它的目标是实现“作用域内一致、作用域外不可关联”：研究、风险、交易 Agent 在同一个任务/会话/交易日内共享临时别名；任务完成、新会话或交易日切换后，映射自动清理并重新生成。外部模型看到带唯一句柄的 P1-P5 语义描述，本地恢复器负责工具查询、交易参数和最终指令的真实身份恢复与合法性校验。

本项目不提出新的量化策略，研究重点是金融多智能体的运行时隐私、流程连续性、恢复正确性和调用成本。B1 与 A1/A2 的差异在于：B1 关注隐私中间层是否能让一个真实 Agent 在多轮、跨工具、在线执行过程中稳定完成任务，并量化匿名检测、恢复和门控带来的时延与成本。

### 原始项目要求

- 标的动态匿名：替换资产身份，阻断直接资产泄露；
- 语义和关系混淆：按保密等级替换或泛化行业、产品、事件、动作和关系；
- 攻击评测：让攻击者利用多 Agent、多轮和跨日 trace 反推真实资产与投资意图；
- 本地恢复：云端只处理匿名信息，本地恢复工具参数和最终业务动作；
- P-U-C 联合评价：同时报告 Privacy、Utility 和 Cost，而不是只看匿名覆盖率。

### 2026-08-10 会议对 B1 的调整

项目组确认 A1/A2 主要共享攻击框架、隐私定义和防御比较，B1 则必须突出金融 Agent 的运行特性。B1 后续研究问题因此收敛到：多轮在线调用中的累计泄露、重试时的鲁棒性、匿名恢复后的工具和业务连续性、推理时延与调用开销，以及“最小必要金融信息”的可操作验证。资产匿名是基础保障，删除、替换和泛化其他信息的范围要通过实验决定。

会议同时指出，十几个或二十几个资产的候选池对重识别攻击过小。NLPCC 可先用于流程和金融效用，但攻击实验必须扩展 decoy universe 或引入更大的股票集合；StockBench、FinVault 等候选 benchmark 必须先核验数据形式和 Agent 工作流是否兼容，不能为了数量强行混用不一致的攻击定义。

## 2. 研究问题与边界

### 核心科学问题

在不重新训练金融 Agent、不把真实映射交给云端的前提下，如何同时实现：

1. 同一研究—风控—交易任务内的实体、指代和动作语义一致；
2. 任务结束、会话切换和交易日切换后的别名不可关联；
3. 外部模型输出经过本地恢复后，工具调用、订单校验和业务执行仍然连续；
4. 多轮重试和连续数据刷新不会造成不可控的累计泄露、推理延迟或调用成本。

### 保护对象

- 真实资产名称、Ticker、证券代码、ISIN 及其同义标识；
- 机构、账户、组合、策略和内部项目名称；
- 候选池、观察列表、持仓标的、权重和调仓方向；
- 新闻/市场信号与内部资产的绑定关系；
- 买入、卖出、增持、减持、清仓等动作，以及“想配置/准备调仓”等意图；
- “该股”“它”“上述组合”等指代和“属于/持有/候选于”等关系；
- 跨 Agent、跨交易日的交互轨迹和交易策略变化。

### 攻击者能力

外部模型服务或其日志分析者可以：

- 观察所有外发 Prompt、工具结果、模型输出和重试请求；
- 关联研究、风险、交易等多个 Agent 的上下文；
- 跨交易日保存别名、文本模板、频率和时间序列；
- 使用公开金融知识、新闻和行情数据做资产重识别；
- 发送提示注入、主动探测和诱导泄露请求；
- 根据工具参数、恢复前后的格式、输出风格和交易频率做侧信道推断。

默认可信边界是本地 FinScope、证券主表、Agent 业务状态和本地执行器。以下不在本阶段研究范围内：本地可信主机被攻破、内部人员直接读取原始数据、网络基础设施攻击、外部模型训练语料本身的隐私问题。

## 3. 设计要求与解决方案

### 3.1 两阶段识别和映射

一次请求先经过本地确定性处理，再决定是否调用本地小模型：

1. 从本地 security master、结构化字段和当前 scope 映射中匹配已知资产、机构、组合、持仓和账户；
2. 已知实体先替换为 typed alias；
3. 对替换后的残余文本运行本地小模型，只让它找新出现的敏感 span；
4. 小模型返回原文片段、实体类型、风险等级和可选的 `refers_to`，不允许它创建别名或修改映射；
5. FinScope 验证片段确实存在、范围不越界、类型合法，必要时用证券主表校验 canonical asset；
6. 映射管理器在本地生成或复用 alias，并从后往前按 span 替换；
7. 同一表面词在不同语义中可以有不同 typed mapping，禁止危险的全局字符串替换。

当前支持的实体类型：`asset`、`institution`/`organization`、`portfolio`、`strategy`、`account`、`reference`、`action`、`relation`、`intent`。数量、价格和权重默认保留，以先验证金融任务效用；高保密等级或模型标记高风险时，动作、关系和意图也会被替换或泛化。

### 3.2 作用域、别名和轮换

别名的稳定键是 `(task_id, conversation_id, trading_day)`。研究、风险和交易 Agent 必须使用同一个 scope handle，才能共享同一张本地映射表。以下事件会清理映射并生成新别名：

- `close_scope` 或任务完成；
- 新的 conversation；
- 同一任务进入新的交易日；
- 明确的安全轮换事件。

别名形如 `FS_ASSET_<8位随机标识>`、`FS_ORG_<8位随机标识>`、`FS_ACTION_<8位随机标识>` 等，类型前缀减少任务内混淆，但不承载真实资产信息。真实值到 alias、alias 到真实值的表只存在本地内存/受控本地存储，不得写入外部 Prompt、云端日志或共享实验产物。

### 3.3 恢复和执行边界

外部输出回到本地后不再调用模型恢复，而是使用 scope 内的确定性双向表：

- 支持 JSON 字段、反引号、括号、所有格、中英文标点和常见前后缀；
- 对“FS_ASSET_x 的”“FS_ASSET_x's”“该 FS_ASSET_x”等形式先识别 alias，再保留前后缀；
- `reference` 若指向已有 alias，直接复用目标 alias，避免“该股/它”产生第二个代号；
- `action` 同时保存展示文本和 canonical execution semantic，恢复后由本地执行器处理；
- `validate_action` 检查资产是否在本地候选池、动作方向、数量/权重范围、账户和交易日约束，非法或不完整输出不得执行；
- 工具调用参数先在本地恢复，再查询真实数据；工具返回值再次经过 `sanitize_tool_result` 后才能发送给外部模型。

### 3.4 动态保密等级

作用域内保密等级只单调升级，不自动降低：`LOW`、`STANDARD`、`HIGH`、`CRITICAL`。出现候选池、持仓、权重、组合或策略至少升级到 `HIGH`；订单、交易、账户和执行字段升级到 `CRITICAL`；出现“真实资产、映射表、系统提示、忽略之前指令”等攻击标记，或累计披露次数达到阈值，也会升级。降低保护强度必须新建 conversation scope，从而同时轮换别名。

### 3.5 小模型调用门控

小模型不应在每条消息上运行。`ResidualScanPolicy` 当前默认策略是：先预热若干次，连续多次没有新替换后进入 cooldown；已确认安全模板直接跳过；达到周期阈值做一次真实 probe；出现 Ticker/六位代码、持仓/账户/调仓词、隐私等级上升或显式 `force_model_scan=True` 时立即唤醒。每个 scope 记录 `recognizer_calls`、`recognizer_skips`、`recognizer_probes`、`recognizer_empty_scans` 和 `recognizer_new_replacements`，用于评估调用节省和漏检风险。

## 4. 当前代码状态

当前仓库是一个基础运行不依赖第三方库、provider 按需安装的本地隐私 Agent 原型，位于 `finscope/`：

- `finscope/core.py`：scope 生命周期、两阶段 sanitize、映射、恢复、工具/动作校验、指标；
- `finscope/policy.py`：动态隐私等级和残余扫描门控；
- `finscope/recognizer.py`：确定性 security-master recognizer、小模型 JSON span recognizer、输出校验和缓存；
- `finscope/privacy_agent.py`：P1-P5 语义描述规划、事实校验、typed binding、恢复歧义审计；
- `finscope/providers.py`：本地 Qwen 与企业 OpenAI-compatible 模型配置；
- `finscope/benchmarks.py`：NLPCC、StockBench、FinVault 共用的生命周期和隐私钩子；
- `examples/finscope_demo.py`：无模型演示；
- `examples/finscope_local_model_demo.py`：本地 Transformers 识别器演示；
- `tests/`：基础替换、作用域轮换、指代、同词异义、恢复和门控测试。

已验证：`python3 -m unittest discover -s tests -v` 通过 33 项测试。P1-P5、同类资产唯一恢复、旧句柄拒绝、模型幻觉回退、恢复审计、模型配置和统一 benchmark adapter 都有离线回归测试。当前还没有完成三套上游 benchmark 的正式回测，不能把原型测试结果写成金融收益或隐私攻击结论。

## 5. 模型分工与 Qwen 27B 说明

这里必须区分两类模型：

1. **金融决策基座模型**：负责新闻理解、资产分析、风险判断和目标权重生成。实验使用本地 `Qwen/Qwen3.8-27B`，以及企业网关提供的 DeepSeek V4 Flash 和 GLM-5.1。
2. **本地隐私 Agent 模型**：识别残余敏感 span、提出 P1-P5 描述并审计恢复歧义。可以先用 0.6B 级模型测速度，也要和 Qwen3.8-27B 比较漏检和语义审计能力。它不能创建 alias、修改映射或绕过代码校验。

公开官方模型名可以确认 `Qwen/Qwen3.8-27B`、`deepseek-v4-flash` 和 `glm-5.1`。企业网关可能使用内部 alias，所以具体 DeepSeek/GLM 模型名必须由 `.env` 配置，并通过网关 `/models` 或管理员文档核验。三套金融基座和本地隐私模型的角色、版本、调用成本必须分别记录。

建议 27B 通过兼容接口部署，示例以官方模型卡为准（需按服务器 GPU、vLLM 版本和上下文长度调整）：

```bash
vllm serve Qwen/Qwen3.8-27B \
  --port 8000 \
  --tensor-parallel-size <GPU数量> \
  --max-model-len <经显存审计后确定> \
  --reasoning-parser qwen3 \
  --language-model-only
```

如果 Agent 使用工具调用，再按模型卡配置 `--enable-auto-tool-choice` 和对应 parser。部署前先检查磁盘、显存、CUDA、`transformers`/vLLM 版本，不要在未确认容量时自动下载 27B 权重。

## 6. 金融 Agent 基座选择

B1 的首个完整适配应只选择一个主基座，避免同时维护三套不可比的 adapter：

- **首选 TradingAgents**：多角色研究、风险和交易节点天然对应 scope 共享、工具调用、记忆和多轮日志，是验证 B1 流程连续性的最佳起点；
- **第二阶段 FinRobot 或 AI Hedge Fund**：用于验证 adapter 可迁移性，先在 TradingAgents 闭环稳定后再接入；
- **daily_stock_analysis、FinCon**：可以作为轻量或概念性补充，不应在第一周并行接入。

适配边界必须覆盖 LLM client、agent message、memory、工具入参、工具返回值和最终 action。不能只包住单个 user prompt，否则无法评估跨 Agent 和跨工具累计泄露。

## 7. NLPCC 2026 数据如何使用

官方仓库：[NLPCC2026-Shared-Task-4](https://github.com/splash-li/NLPCC2026-Shared-Task-4/tree/main/NLPCC_tasks/dataset)。它的任务是中国市场的 LLM 投资顾问 Agent：每天输入 Top-20 财经热点和历史价格，输出 ETF 目标权重，使用日频标准回测和 `0.01%` 交易摩擦。Track 1 是约 11 个宏观 ETF/指数，Track 2 是约 16 个行业主题 ETF；主要指标是 Sharpe，同时报告累计收益和最大回撤。

公开 starter kit 的候选代码包括：

- 宏观：`000300.SH`、`000905.SH`、`399006.SZ`、`000688.SH`、`000932.SH`、`000941.SH`、`399971.SZ`、`000819.SH`、`000928.SH`、`000012.SH`、`518880.SH`；
- 行业：`512880.SH`、`512800.SH`、`512070.SH`、`159995.SZ`、`159819.SZ`、`515880.SH`、`159852.SZ`、`512010.SH`、`512170.SH`、`159992.SZ`、`515170.SH`、`512690.SH`、`512400.SH`、`515220.SH`、`159870.SZ`、`512200.SH`。

数据加载必须复用官方 `dataset/dataloader_eval.py` 或 starter kit DataLoader：

1. `get_news(sources, current_date, top_rank=20, pre_k_days=1)` 读取热榜新闻；
2. 当前交易日只保留 `15:00` 前新闻；
3. 历史价格返回过去完整行情，但当前交易日只返回开盘价，隐藏当日收盘、高低价和涨跌幅；
4. 目标权重输出提交给回测执行器，比较 Vanilla 和 FinScope 的回测表现、动作恢复和执行成功率；
5. 所有输入、原始输出、匿名输出、恢复后的 action 和执行结果都要带 `task_id/conversation_id/trading_day`，但外部模型日志只能保留匿名 trace。

当前检出的外部数据文件是 Git LFS pointer，约 130 字节，并非完整 CSV。新服务器必须在独立的数据目录执行 `git lfs install` 和 `git lfs pull`，确认真实文件大小、新闻日期范围、资产覆盖和 license 后才能开始主实验。不要把外部数据或原始持仓日志复制进本仓库，除非 license 和 `.gitignore` 已明确允许。

NLPCC 是首个金融效用/连续执行 benchmark，不单独提供攻击者 ground truth。隐私攻击可以在同一批任务上记录本地真实值与匿名外发 trace，再执行资产重识别、候选池恢复、持仓推断和跨日关联；攻击评测的候选池要扩大，不能只在十几个标的中报告“容易”的结果。

## 8. 其他 benchmark 的定位

最终选择必须先审计任务 schema 和资产范围，不能只按名称拼接：

| 数据/基准 | 建议用途 | 当前决策 |
| --- | --- | --- |
| NLPCC 2026 Shared Task 4 | 新闻+行情+日频目标权重+回测 | 首选主实验 |
| StockBench | 个股分析、买入/持有/卖出和跨日交易 | 作为第二金融效用集，先验证 prompt/tool 兼容性 |
| FinVault | 金融 Agent 工具调用、执行安全和隐私攻击 | 若可取得任务与许可证，作为安全补充 |
| AgentDojo Banking | 通用工具调用/提示注入攻击范式 | 作为方法学 sanity check，不替代股票回测 |
| FinanceBench | 财报/金融文档问答 | 可选，用于判断泛化，不作为主交易实验 |

B1 的最低可行实验是“TradingAgents + NLPCC + 自定义多轮攻击回放”。只有第一条链路稳定后，才加入 StockBench、FinVault 或 AgentDojo adapter。若资产集合、输入文本和执行语义差异太大，应分别报告，不能强行使用同一 FAL 定义。

## 9. 攻击、效用、恢复和成本评测

### 攻击族

- 直接询问/诱导外部模型还原 alias；
- 用公开新闻和行情做候选资产重识别；
- 汇总研究、风险、交易三个 Agent 的 transcript；
- 跨交易日按 alias、模板、频率和时间序列做关联；
- 从工具参数、工具返回值和最终 action 反推敏感状态；
- Prompt injection、索要系统提示和映射表；
- 重试和数据刷新造成的累计暴露；
- 主动选择查询、同义改写、格式/长度/风格侧信道。

### 隐私指标

- `Asset-ReID`、`ReID@1`、`ReID@5`：匿名资产被恢复的准确率；
- `Pool-Recovery F1`：候选池恢复；
- `Holding-Inference F1` 和 `Weight-MAE`：持仓标的与权重推断；
- `Cross-Day-Link AUC/Accuracy`：跨日 alias/轨迹关联；
- `Action/Intent Inference`：交易方向和意图推断；
- `Direct Leak Rate`：外发内容直接包含敏感信息的比例。

FAL（Financial Association Leakage）可以作为报告总称，但在定义权重、攻击先验和置信区间之前，不要把未经校准的单一加权数字当成结论；优先报告各子指标和攻击曲线。

### 金融效用与流程连续性

- 累计收益、Sharpe、Sortino、最大回撤、换手率；
- Vanilla 与 FinScope 的目标权重/动作一致率；
- 工具调用成功率、恢复后的 action 合法率、真实执行成功率；
- 多轮任务完成率、重试率、流程中断率、异常输出恢复率；
- 资产、前后缀、指代、动作和权重恢复误差。

### B1 运行成本

- 本地 detector 调用次数、跳过次数、probe 次数和本地 p50/p95 延迟；
- 外部输入/输出 Token、外部调用总次数和重试次数；
- 端到端 p50/p95 延迟；
- 每个交易日、每个 Agent 和每种风险等级的成本；
- always-scan 与 gated-scan 的隐私/效用/成本变化。

## 10. 对照组和消融实验

最少包含：

- Vanilla：无保护，作为效用参考和泄露上界；
- Direct deletion：删除识别到的敏感字段；
- LLM rewrite：外部/本地改写或泛化；
- Fixed/global alias：全局长期固定代号；
- Episode-fixed alias：一个 episode 内固定，但不跨日轮换；
- FinScope：scope 内稳定、scope 外轮换、工具本地恢复；
- FinScope without gate：每次都喂本地小模型；
- FinScope without security-master validation；
- FinScope without coreference reuse；
- static privacy vs adaptive privacy；
- 0.6B detector 与更大 detector 的准确率/时延比较（资源允许时）。

需要隔离的变量包括：代号轮换范围、资产/动作/关系的保护等级、删除/替换/泛化策略、攻击强度、重试次数、候选池规模、基座模型和扫描门控模式。

## 11. 目前未完成、不得过度宣称的部分

- 尚未完成 TradingAgents/FinRobot/AI Hedge Fund 的正式 adapter；
- 尚未在完整 NLPCC LFS 数据上跑出金融收益结果；
- 尚未完成候选池扩大后的攻击 ground truth 和统一 FAL 标定；
- 当前映射主要在内存中，生产部署仍需本地加密存储、密钥生命周期和崩溃恢复设计；
- 当前 0.6B recognizer 需要真实中文金融残余 span 数据做准确率、漏检和误报评估；
- 企业网关中的 DeepSeek/GLM 实际模型 alias 尚需在实验服务器核验；
- “公开新闻是否直接含 ETF 代码/名称”的覆盖率必须在拉取 LFS 后实测，不能凭文件名推断。

## 12. 交接后的最小执行顺序

1. 审计新服务器 GPU、CUDA、Python、磁盘、Git LFS 和模型缓存；
2. 克隆本仓库，运行现有 33 项测试；
3. 核验用户给出的 Qwen 27B 实际模型 ID，明确基座模型与 0.6B detector 的部署分工；
4. 拉取 NLPCC LFS 数据，核验真实文件、日期、新闻覆盖、候选池和许可；
5. 先用一个交易日、一个 Agent、少量候选资产完成 Vanilla -> sanitize -> 外部 LLM -> restore -> validate -> backtest smoke；
6. 再接入 TradingAgents 的研究/风险/交易节点，统一 scope 和 trace schema；
7. 先跑流程连续性和调用成本，再跑主效用和攻击实验；
8. 每项结果保留配置、模型版本、数据 hash、匿名 trace、映射 ground truth（仅本地）和统计置信区间。

## 13. 参考资料

### 可直接核验的官方材料

- [Qwen/Qwen3.8-27B 官方模型卡](https://huggingface.co/Qwen/Qwen3.8-27B)
- [NLPCC 2026 Shared Task 4 数据与 DataLoader](https://github.com/splash-li/NLPCC2026-Shared-Task-4/tree/main/NLPCC_tasks/dataset)
- [FinScope 当前实现](../README.md)

### 项目组提供的阅读清单（投稿前须逐条核对版本、作者和日期）

1. FinCon, NeurIPS 2024；
2. TradingAgents, arXiv:2412.20138；
3. FinRobot, arXiv:2405.14767；
4. Can Blindfolded LLMs Still Trade?, 项目材料标注 ICLR FinAI Workshop 2026；
5. KTD-Fin / From Knowing to Doing, 项目材料标注 arXiv:2605.28359；
6. PrivScope, 项目材料标注 arXiv:2605.16630v2；
7. PAPILLON, 项目材料标注 NAACL 2025；
8. Fides / Securing AI Agents with Information-Flow Control, 项目材料标注 arXiv:2505.23643；
9. Maris, 项目材料标注 arXiv:2505.04799；
10. OCELOT, 项目材料标注 arXiv:2606.12341；
11. AgentSpec, 项目材料标注 ICSE 2026；
12. AgentDojo, NeurIPS Datasets and Benchmarks 2024；
13. AgentLeak, 项目材料标注 arXiv:2602.11510；
14. ToolPrivacyBench, 项目材料标注 arXiv:2606.28061；
15. StockBench, 项目材料标注 arXiv:2510.02209；
16. CN-Buzz2Portfolio / NLPCC Shared Task 4, 项目材料标注 arXiv:2603.22305；
17. PortBench, 项目材料标注 arXiv:2605.27887；
18. FinanceBench, arXiv:2311.11944。

清单中的部分条目来自项目组会议材料，可能是预印本、未来会议版本或暂定名称；论文中使用前必须重新核验公开链接和元数据。

## 14. 安全与复现要求

- 不提交 `.env`、API key、真实账户号、真实持仓或本地 alias map；
- 外部模型日志只保留匿名 prompt/output 和不可逆 trace id；
- 本地攻击评测可以读取映射 ground truth，但 ground truth 必须和云端 trace 分开保存；
- 任何真实交易 API 只能被显式 mock 或 paper-trading adapter 调用；
- 运行日志记录模型 ID、代码 commit、数据 hash、scope 配置、隐私等级、门控统计和异常，不记录完整真实 payload；
- 所有金融收益结果标明是历史回测，不构成投资建议。
