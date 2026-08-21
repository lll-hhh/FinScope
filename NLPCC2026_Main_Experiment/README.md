# FinScope × NLPCC2026 Shared Task 4 主实验

本目录集中保存 FinScope 在 NLPCC2026 Shared Task 4（macro track）上的实验适配代码、三组全年原始结果、指标汇总与阶段性结论。

## 实验设置

- 时间区间：2025-01-02 至 2025-12-31，共 243 个交易日
- 新闻设置：`top-rank=2`
- 模型：Qwen/Qwen3-8B，32K 上下文
- 初始资金：100,000
- 对照条件：
  - `original`：敏感证券名称和代码以明文发给模型；
  - `direct`：使用全局稳定的直接代号映射；
  - `finscope`：在完整多智能体决策周期内共享类型化代号，并在下一交易日前轮换，在本地恢复为可执行代码。

这是用于方法比较的研究主实验，不是官方 Top-20 leaderboard 成绩。

## 目录结构

```text
NLPCC2026_Main_Experiment/
├── code/                       # 隐私代理、结果汇总和对比脚本
└── results/
    ├── RESULTS_ZH.md           # 中文结论、限制与解释边界
    ├── comparison.md           # 核心指标表
    ├── comparison.json         # 机器可读的完整汇总
    ├── original_valid/         # 明文基线原始结果与摘要
    ├── direct_valid/           # 全局直接映射原始结果与摘要
    └── finscope/               # FinScope 原始结果与摘要
```

## 核心结果

| 条件 | 累计收益率 | Sharpe（重算） | 最大回撤（重算） | 执行成功率 | 敏感标识外发率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 23.7748% | 1.9063 | -6.4239% | 83.7116% | 100.0000% |
| Direct | 33.0146% | 1.9457 | -7.8722% | 84.7118% | **0.0000%** |
| FinScope | **34.5010%** | **2.2858** | **-5.1400%** | **87.5164%** | 0.6810% |

三组均完成 243 个交易日和 11,192 次代理请求，代理请求错误为 0。FinScope 的收益、风险和执行指标在本次单次运行中最好，但仍存在 0.6810% 的敏感标识残余外发，不能据此宣称其纯匿名化强度优于 Direct。详细原因、交易统计和解释边界见 [`results/RESULTS_ZH.md`](results/RESULTS_ZH.md)。

## 复现实验汇总

从仓库根目录执行：

```bash
python NLPCC2026_Main_Experiment/code/summarize_results.py \
  --result <condition>/result.json \
  --audit <condition>/proxy.jsonl \
  --output <condition>/summary.json

python NLPCC2026_Main_Experiment/code/compare_results.py \
  --root NLPCC2026_Main_Experiment/results \
  --output-json NLPCC2026_Main_Experiment/results/comparison.json \
  --output-md NLPCC2026_Main_Experiment/results/comparison.md
```

原始隐私审计 `proxy.jsonl` 含完整模型请求记录且体积较大，未上传到本目录；仓库中保留的是由审计日志计算出的 `summary.json` 和对比结果。完整财务回测结果保存在各条件的 `result.json` 中。

## 当前限制

- 当前仅有一次随机运行，收益差异需要多随机种子与置信区间验证。
- `top-rank=2` 不是官方 Top-20 完整配置。
- FinScope 的残余外发主要来自“沪深300ETF”等数字与 `ETF` 连写时的边界识别问题；修复后应重新运行隐私消融。
