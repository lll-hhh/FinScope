# 交给另一台服务器 Agent 的启动提示词

下面的内容可以直接复制给新服务器上的 coding/research agent。它假定该 Agent 可以访问 GitHub、可以运行本地命令，并且有权限在指定服务器上安装依赖；它不假定当前服务器的路径、GPU、模型缓存或数据已经存在。

```text
你现在接手 FinScope 项目 B1。请把自己当成负责“可运行实验闭环”的工程研究 Agent，而不是只写方案的助手。

项目仓库：git@github.com:lll-hhh/FinScope.git
主分支：main
项目定位：面向金融多智能体的本地隐私 Agent。核心目标是“同一任务/会话/交易日内代号一致，任务外/跨日不可关联”，同时保证外部大模型输出经过本地恢复后，工具调用、风控和交易执行仍能连续完成。
完整背景、设计、指标和当前限制：先阅读 docs/project_background.md、README.md、docs/finscope_quickstart.md。

一、先做环境审计，不要直接下载模型或跑长实验

1. 克隆仓库并确认当前 commit、工作区和远端：
   git clone git@github.com:lll-hhh/FinScope.git
   cd FinScope
   git status --short
   git log --oneline -5
2. 检查：nvidia-smi、CUDA、Python 版本、磁盘剩余空间、可用显存、torch/transformers/vLLM/SGLang 版本、git-lfs 是否可用。
3. 不要把 API key、真实账户、真实持仓、.env 或完整本地映射表写入仓库或外部模型日志。
4. 运行现有测试：
   python3 -m unittest discover -s tests -v
   如果测试失败，先定位并记录，不要为了跑新实验删除旧测试。

二、核对三套模型并区分模型角色

本地主模型使用公开的 `Qwen/Qwen3.8-27B`，通过 vLLM/SGLang 的 OpenAI-compatible endpoint 部署。另两个金融基座是企业网关中的 DeepSeek V4 Flash 和 GLM-5.1。网关 alias 可能与官方 `deepseek-v4-flash`、`glm-5.1` 不同，必须查询 `/models` 或管理员说明后分别填入 `EFUNDS_DEEPSEEK_MODEL`、`EFUNDS_GLM_MODEL`。所有 key 和账户 Header 只放环境变量，不得写入文件、日志或提交。

模型角色必须分开：

- 三套模型作为金融 Agent 的决策基座，负责新闻/行情理解、研究、风险判断和目标权重/交易 action；
- 本地隐私模型负责残余 span、P1-P5 描述和恢复语义审计。先在 NLPCC 固定 Qwen3.8-27B 任务模型，比较 Qwen3.5-0.8B/2B/4B/9B 的严格成功率、字段规范化、漏检、时延和成本；Qwen3.8-27B 只能作为任务模型或上界参考，不能作为最终本地隐私 Agent。它不能创建 alias、不能修改映射、不能绕过安全主表校验；严格实验禁止整套 deterministic fallback 冒充模型成功。

先审计 GPU 后再决定 tensor parallel 和 max context，不要在没有预算和磁盘确认时下载权重。复制 `.env.example` 后只在密钥管理器或本地 `.env` 中填值，且确认 `.env` 被 Git 忽略。

三、理解现有 FinScope 实现后再接 Agent

必须读：

- finscope/core.py：scope、两阶段 sanitize、映射、restore、validate_action；
- finscope/policy.py：AdaptivePrivacyPolicy、ResidualScanPolicy、扫描门控；
- finscope/recognizer.py：JSON span detector、校验、security-master fallback；
- finscope/privacy_agent.py：五级语义规划、句柄绑定、恢复和歧义审计；
- finscope/providers.py：Qwen、DeepSeek、GLM 配置；
- finscope/benchmarks.py：三个 benchmark 的统一隐私钩子；
- tests/ 和 examples/。

你需要保留这些约束：

1. 先用本地 security master 和现有 scope mapping 替换已知实体，再把残余文本交给本地小模型；
2. 小模型只返回原文 span、type、risk、可选 refers_to，不得生成或修改别名；
3. alias 在 (task_id, conversation_id, trading_day) 内稳定，close/new conversation/new trading day 后清理并轮换；
4. research、risk、trading Agent 共享同一个 scope handle；
5. 工具参数本地 restore 后才查询真实数据，工具结果必须再次 sanitize；
6. 外部 output 只能由本地 restore 和 validate_action 处理，非法 action 不执行；
7. 小模型不是每条消息都调用：保留 warmup、empty-scan cooldown、safe-template skip、periodic probe、risk wake 和 force scan；
8. 映射表和真实 payload 只留本地，云端只看到匿名文本。

四、第一阶段只做一个最小、可验证的金融闭环

主基座建议先选 TradingAgents，因为它有研究、风险和交易等多角色节点，最适合验证 B1 的多轮/多 Agent/工具调用连续性。不要第一天同时接 TradingAgents、FinRobot 和 AI Hedge Fund。TradingAgents 闭环稳定后，再选 FinRobot 或 AI Hedge Fund 做第二 adapter。

首个 benchmark 使用 NLPCC 2026 Shared Task 4：

- 每个交易日输入官方 DataLoader 产生的 Top-20 新闻和防未来泄露的历史行情；
- 输出 ETF 目标权重，交给官方/兼容回测执行器；
- 先跑一个交易日、一个 Agent、少量候选资产的 smoke，再扩展到完整年度；
- 必须复用官方 DataLoader 规则：当天新闻只取 15:00 前；当前日行情只给开盘价；不能泄露当日收盘、高低价和涨跌幅；
- 数据仓库使用 Git LFS pointer，先在独立数据目录执行 git lfs install/git lfs pull，确认实际文件、日期覆盖、新闻源、候选资产和许可；不要凭文件名声称已经拥有完整数据。

第一条真实 pipeline 必须有清晰边界：

官方 DataLoader -> TradingAgents 原始输入 -> FinScope.sanitize_messages/tool_result -> 27B endpoint -> FinScope.restore_output -> validate_action -> mock/backtest executor。

同时保存以下 trace（真实映射只在本地）：scope ID、交易日、输入字段类型、匿名 prompt/output、恢复后的 action、合法性、执行结果、模型调用次数、detector 调用/跳过/probe、延迟和 token。不要把原始真实 prompt 和 mapping 写入云端日志。

五、必须先实现/确认的交付物

按下面顺序做，不要跳过审计：

1. environment_report.md：硬件、软件、模型 ID、可用磁盘/显存、数据是否成功拉取；
2. baseline_decision.md：为什么先选 TradingAgents，另两个框架为何延期；
3. NLPCC adapter：至少支持一个交易日的新闻、行情、目标权重和 mock/backtest；
4. trace schema：匿名外发 trace、本地映射 ground truth、恢复和执行结果分离；
5. Vanilla vs FinScope smoke：验证任务完成、工具参数恢复、action 合法、scope 内 alias 一致、换日后 alias 轮换；
6. detector gating smoke：证明稳定输入会 skip，风险关键词/隐私升级/周期 probe 会重新调用 0.6B；
7. 只有上述产物通过后，才开始主实验和攻击实验。

六、攻击与评测先按 B1 特性设计

攻击至少覆盖：直接诱导重识别、公开新闻/行情关联、研究/风险/交易 transcript 聚合、跨日 alias 关联、工具参数/工具结果泄露、prompt injection、重试累计泄露、主动选择查询和格式侧信道。

隐私结果优先报告子指标：Asset-ReID/ReID@1/@5、Pool-Recovery F1、Holding-Inference F1、Weight-MAE、Cross-Day-Link AUC、Action/Intent Inference 和 Direct Leak Rate。只有在明确权重、攻击先验和置信区间后才汇总 FAL，不能先编一个单一分数。

效用与连续性报告：累计收益、Sharpe、Sortino、最大回撤、换手率、Vanilla/FinScope 决策一致率、工具调用成功率、恢复合法率、真实执行成功率、多轮完成率、流程中断率和重试率。

成本报告：本地 detector 调用/跳过/probe、p50/p95 本地延迟、外部 token、外部调用次数、重试次数和端到端 p50/p95。

对照/消融至少包括：Vanilla、direct deletion、LLM rewrite、global fixed alias、episode-fixed alias、FinScope、always-scan、无 security-master validation、无 coreference reuse、static privacy、adaptive privacy。不要同时改变模型、数据、候选池和 alias 策略，否则无法解释结果。

七、工程和安全规则

- 不执行真实交易，只用 mock/paper-trading/backtest；
- 不上传 .env、API key、真实账户、真实持仓、完整 mapping 或未获许可的数据；
- 不把“模型没有主动泄露”写成隐私证明，必须有攻击者实验；
- 不把原型测试通过写成金融收益已经提升；
- 所有实验记录 commit、模型 ID/version、数据 hash、配置和失败案例；
- 任何发现的 bug 先增加回归测试，再修实现；
- 代码改动小步提交，提交信息说明行为变化；
- 长时间任务每 30-60 秒汇报一次状态，遇到模型名、数据 license、显存或 benchmark schema 不确定时先报告，不自行编造。

八、完成标准

当且仅当以下条件满足，才说“最小实现完成”：

1. 当前 FinScope 全部测试通过；
2. 一个真实本地/自建 27B endpoint 可被 Agent 调用，或明确记录 endpoint 阻塞原因；
3. NLPCC 至少一个交易日完成 Vanilla 和 FinScope 两条链路；
4. 研究/风险/交易在同一 scope 内 alias 一致，换 conversation/trading day 后不可复用旧 alias；
5. 工具参数和最终 action 本地恢复、校验并成功进入 mock/backtest；
6. detector gating、隐私等级升级、重试和失败输出有可观察指标；
7. README/文档、配置、运行命令和失败限制写清楚；
8. 任何结论都标明是 smoke、主实验还是正式统计结果。

现在先执行第一阶段：环境审计、读文档、跑测试、核对模型和数据，不要直接开始长时间回测。完成后先汇报审计结果和下一步最小修改列表。
```
