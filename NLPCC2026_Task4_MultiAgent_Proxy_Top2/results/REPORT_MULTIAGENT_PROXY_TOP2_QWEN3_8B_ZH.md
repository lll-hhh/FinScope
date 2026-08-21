# Official-Starter Multi-Agent Proxy Integration Table（Top-2）

- Experiment ID：`multiagent-proxy-top2-qwen3-8b-2025`
- Pipeline：NLPCC2026 Task 4 官方 Agent-Bench 多智能体 starter pipeline，外接隐私代理
- Model：`Qwen/Qwen3-8B`，32K 上下文
- Window：`2025-01-02` 至 `2025-12-31`，共 243 个交易日
- Data：官方新闻与 ETF/指数价格；新闻检索为 `top-rank=2`
- Trading：CNY 100,000 初始资金，沿用官方执行和回测流程

本报告与仓库既有的 [`nlpcc_real_2025_qwen38_p3.md`](../../benchmarks/results/nlpcc_real_2025_qwen38_p3.md) 属于两项不同实验。既有报告采用仓库自定义单步决策 runner、Qwen3.8-27B 和 Top-20；本报告考察 Top-2 官方多智能体调用链中的代理边界集成。两份报告的收益率、泄漏率和延迟不能直接横向比较。

## Main Table

| Method | Return ↑ | Sharpe ↑ | MDD ↓ | Valid execution ↑ | Proxy success ↑ | Identifier exposure ↓ | Prompt tokens ↓ | Mean latency ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plaintext_original | 23.77% | 1.906 | 6.42% | 83.71% | 100.00% | 100.000% | 9,547,533 | 2.301 s |
| global_direct_alias | 33.01% | 1.946 | 7.87% | 84.71% | 100.00% | **0.000%** | 9,607,226 | 2.244 s |
| scoped_finscope_alias | **34.50%** | **2.286** | **5.14%** | **87.52%** | 100.00% | 0.681% | 9,648,496 | **2.114 s** |

## Financial Detail

| Method | Final CNY | Ann. return | Ann. vol. | Calmar | Positive days | VaR 95 | CVaR 95 | Best day | Worst day | Max DD duration | Executed trades | Commission |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plaintext_original | 123,774.82 | 24.53% | 12.04% | 3.819 | 55.8% | 1.00% | 1.80% | 2.64% | -4.08% | 76 | 627 | 220.14 |
| global_direct_alias | 133,014.56 | 34.10% | 15.93% | 4.332 | 55.0% | 1.42% | 2.24% | 3.95% | -5.51% | 58 | 676 | 242.27 |
| scoped_finscope_alias | **134,501.04** | **35.64%** | 13.94% | **6.935** | 54.1% | 1.26% | 2.03% | 2.84% | -4.18% | 60 | 666 | 257.82 |

Sharpe、MDD、波动率、Calmar、VaR 和 CVaR 均从官方 `portfolio_value_history` 的每日最后一条净值重新计算；官方结果文件直接提供累计收益、年化收益和最终净值。

## Multi-Agent Continuity And Utility

| Method | Complete days | Trade-submit days | All requests | News calls | Sentiment calls | Trading calls | Proxy errors | News-summary failures | Attempted trades | Executed | Rejected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plaintext_original | 243 | 239 | 11,192 | 10,706 | 243 | 243 | 0 | 27 | 749 | 627 | 122 |
| global_direct_alias | 243 | 242 | 11,192 | 10,706 | 243 | 243 | 0 | 27 | 798 | 676 | 122 |
| scoped_finscope_alias | 243 | 242 | 11,192 | 10,706 | 243 | 243 | 0 | 27 | 761 | 666 | 95 |

`Trade-submit days` 少于 243 表示代理在部分交易日选择持有，没有提交交易，并非实验缺失。三组均出现 27 条相同类型的新闻摘要解析失败，流程采用空摘要继续运行，未造成交易日中断；该错误来自底层新闻摘要结果为 `None`，不是隐私代理请求失败。

## Privacy

| Method | Sensitive-input requests | Leaking requests | Input identifiers | Outbound identifiers | Exposure rate ↓ | Alias occurrences | Mapping lifecycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| plaintext_original | 1,998 | 1,998 | 24,415 | 24,415 | 100.000% | 0 | 原始标识跨调用保持不变 |
| global_direct_alias | 1,998 | 0 | 22,806 | 0 | **0.000%** | 22,809 | 全年使用稳定全局代号 |
| scoped_finscope_alias | 1,998 | 62 | 22,321 | 152 | 0.681% | 22,169 | 同一决策周期共享，下一交易日轮换 |

隐私指标统计官方候选证券名称和代码在代理输入与外发文本中的字面出现次数，不等同于语义重识别攻击成功率。FinScope 的 152 次残余外发主要来自“沪深300ETF”“中证500ETF”“科创50ETF”等数字与 `ETF` 连写时的边界识别问题；因此当前结果不能宣称 FinScope 的纯匿名化强度优于全局直接映射。

## Cost And Latency

| Method | Total input tok. | Avg input | Total output tok. | Avg output | Mean latency s | Median latency s | P95 latency s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plaintext_original | 9,547,533 | 853.1 | 735,229 | 65.7 | 2.301 | 1.238 | 2.464 |
| global_direct_alias | 9,607,226 | 858.4 | 727,898 | 65.0 | 2.244 | **1.174** | 2.499 |
| scoped_finscope_alias | 9,648,496 | 862.1 | 742,117 | 66.3 | **2.114** | 1.206 | **2.196** |

## Rejection Breakdown

- **plaintext_original**：`cannot sell an empty holding` 62；`insufficient capital` 60。
- **global_direct_alias**：`cannot sell an empty holding` 15；`insufficient capital` 107。
- **scoped_finscope_alias**：`cannot sell an empty holding` 39；`insufficient capital` 55；`no closing price available` 1。

## Result Interpretation

- 相对 `plaintext_original`，`scoped_finscope_alias` 的累计收益高 10.73 个百分点，Sharpe 高 0.380，最大回撤收窄 1.28 个百分点，执行成功率高 3.80 个百分点。
- 相对 `global_direct_alias`，`scoped_finscope_alias` 的累计收益高 1.49 个百分点，Sharpe 高 0.340，最大回撤收窄 2.73 个百分点，执行成功率高 2.80 个百分点。
- 这些效用差异来自独立生成的单次全年轨迹，只能作为初步正面证据，不能解释为隐私机制带来确定的因果收益。
- 本实验更直接支持的结论是：FinScope 中间层可以连续包裹新闻、情绪和交易三个代理阶段，在 11,192 次外部调用中完成作用域代号共享、响应恢复和结果执行，没有造成代理层错误或交易日中断。

## Not Measured In This Run

多随机种子均值与置信区间、官方 Top-20 配置、与明文轨迹配对的动作一致率、攻击者驱动的 Asset-ReID@1/@5、Pool-Recovery F1、Holding/Action Inference、跨日链接 AUC、边界规则修复后的重跑结果，以及作用域轮换、最小上下文和执行校验的独立消融。

本实验是全年官方 starter pipeline 的 Top-2 集成研究，不是官方 leaderboard 提交；语义重识别风险需要单独的攻击实验评估。
