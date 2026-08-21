# NLPCC2026 Task 4 官方 Starter 多智能体代理边界实验

**实验标识：`multiagent-proxy-top2-qwen3-8b-2025`**

本目录保存的是一项独立的“官方多智能体 starter pipeline 集成实验”：在不改写官方新闻、情绪、交易和回测流程的前提下，将 Original、全局直接代号和 FinScope 作用域代号三种边界策略接入每一次外部模型调用。

## 与仓库既有 NLPCC 实验的区别

本目录**不是** [`benchmarks/results/nlpcc_real_2025_qwen38_p3.md`](../benchmarks/results/nlpcc_real_2025_qwen38_p3.md) 的重复结果，也不应与其数值直接合并比较。

| 维度 | 仓库既有 `nlpcc_real_2025_qwen38_p3` | 本目录 `multiagent-proxy-top2-qwen3-8b-2025` |
| --- | --- | --- |
| 运行入口 | 仓库自定义 `benchmarks/run_nlpcc_real.py` | NLPCC 官方 Agent-Bench starter pipeline + 外部隐私代理 |
| 模型 | Qwen3.8-27B | Qwen3-8B，32K 上下文 |
| 新闻密度 | Top-20 | Top-2 |
| 决策结构 | 每日单次资产动作决策 | 新闻代理、情绪代理、交易代理组成的多阶段流程 |
| 全年模型调用 | 约每方法 243 次核心决策 | 每条件 11,192 次：10,706 新闻 + 243 情绪 + 243 交易 |
| 方法组 | vanilla / deletion / fixed_alias / finscope | plaintext original / global direct alias / scoped FinScope alias |
| 主要问题 | 不同隐私方法对单步决策的效用与隐私影响 | 隐私中间层能否贯穿真实多智能体调用链并恢复可执行结果 |
| 隐私口径 | 按交易日统计直接泄漏与跨日链接 | 按代理调用审计敏感标识输入/外发出现次数 |

由于模型、新闻数量、提示词、调用粒度、交易动作定义和隐私统计口径均不同，两份报告中的收益率、泄漏率和延迟不能作为同一张主表中的可比方法结果。

## 本实验设置

- 区间：2025-01-02 至 2025-12-31，共 243 个交易日
- 任务：NLPCC2026 Shared Task 4，macro track
- 新闻设置：`top-rank=2`
- 模型：Qwen/Qwen3-8B，32K 上下文
- 初始资金：CNY 100,000
- 三个条件：
  - `plaintext_original`：证券名称和代码以明文进入外部模型；
  - `global_direct_alias`：整个实验使用全局稳定的直接代号；
  - `scoped_finscope_alias`：一个交易日的新闻、情绪和交易代理共享类型化代号，下一交易日前轮换，并在本地恢复为交易代码。

这是 Top-2 的多智能体管线集成研究，不是官方 Top-20 leaderboard 成绩。

## 目录结构

```text
NLPCC2026_Task4_MultiAgent_Proxy_Top2/
├── README.md
├── code/                                      # 代理适配与汇总脚本
└── results/
    ├── REPORT_MULTIAGENT_PROXY_TOP2_QWEN3_8B_ZH.md
    ├── multiagent_proxy_top2_comparison.md
    ├── multiagent_proxy_top2_comparison.json
    ├── plaintext_original/
    ├── global_direct_alias/
    └── scoped_finscope_alias/
```

## 核心结果

| 条件 | 累计收益率 | Sharpe（重算） | 最大回撤（重算） | 执行成功率 | 敏感标识外发率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plaintext Original | 23.7748% | 1.9063 | -6.4239% | 83.7116% | 100.0000% |
| Global Direct Alias | 33.0146% | 1.9457 | -7.8722% | 84.7118% | **0.0000%** |
| Scoped FinScope Alias | **34.5010%** | **2.2858** | **-5.1400%** | **87.5164%** | 0.6810% |

三组均覆盖完整 243 个交易日，每组完成 11,192 次代理调用且代理错误为 0。FinScope 在本次单次运行中的收益、风险和执行指标最好，但仍有 0.6810% 的敏感标识残余外发，因此不能宣称其纯匿名化强度优于全局直接映射。

详细统计、限制和结论见 [`results/REPORT_MULTIAGENT_PROXY_TOP2_QWEN3_8B_ZH.md`](results/REPORT_MULTIAGENT_PROXY_TOP2_QWEN3_8B_ZH.md)。

## 复现汇总

从仓库根目录执行：

```bash
python NLPCC2026_Task4_MultiAgent_Proxy_Top2/code/summarize_results.py \
  --result <condition>/result.json \
  --audit <condition>/proxy.jsonl \
  --output <condition>/summary.json

python NLPCC2026_Task4_MultiAgent_Proxy_Top2/code/compare_results.py \
  --root NLPCC2026_Task4_MultiAgent_Proxy_Top2/results \
  --output-json NLPCC2026_Task4_MultiAgent_Proxy_Top2/results/multiagent_proxy_top2_comparison.json \
  --output-md NLPCC2026_Task4_MultiAgent_Proxy_Top2/results/multiagent_proxy_top2_comparison.md
```

原始隐私审计 `proxy.jsonl` 包含完整模型请求记录且体积较大，未提交到本目录；这里保留由审计日志计算的 `summary.json`、完整财务回测 `result.json` 和统一对比结果。

## 解释边界

- 当前是单次随机运行，需要多随机种子与置信区间验证。
- Top-2 结果不能替代官方 Top-20 配置。
- FinScope 残余外发主要来自“沪深300ETF”等数字与 `ETF` 连写时的边界识别问题；修复后需要重新运行隐私消融。
- 本实验回答的是“隐私中间层能否贯穿官方多智能体调用链”，仓库既有实验回答的是“不同隐私方法如何影响单步投资动作”，两者应作为互补证据分别报告。
