# COLING B1 补充实验执行版

更新日期：2026-08-23。

所有补充实验固定使用 NLPCC 2026 Track 1 public A-set。任务模型固定为 Qwen3.8-27B，本地隐私 Agent 从 10 个不超过 4B 的模型中只用开发集选出一个，之后测试集固定使用该模型。`TBD` 表示尚未完成正式测试，不表示 0；双资产 smoke、单日 smoke 和单元测试不填入以下表格。

这些表格不替代主表。主表回答“不同 Benchmark、任务模型和方法的最终结果如何”；下面的表格分别解释动态披露、长程替换和主方法组件为什么有效。

## 第一组：动态披露

### 表 A1：动态披露与固定披露

**问题：** 动态方案能否在固定 P1-P5 之间取得更好的效用、隐私、安全和成本折中。

每一行使用同一测试窗口；固定行全程使用对应等级，动态行由本地 Agent 根据角色、阶段、风险和累计披露量选择等级。

| 方案 | 平均选择等级 | Sharpe | Return | MDD | Valid Output | ReID@1 | Link AUC | Unsafe Repair | Token Delta | E2E p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 固定 P1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 固定 P2 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 固定 P3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 固定 P4 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 固定 P5 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 动态披露 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### 表 A2：动态决策是否使用场景状态

**问题：** 动态选择是否真的受到任务阶段、风险和历史披露影响，而不是固定返回一个等级。

对同一条输入只改变一个状态因素，并记录选择等级和触发原因；随后运行同一任务，检查状态变化是否带来可解释的安全或成本变化。

| 场景 | 去掉的状态 | 选择等级 | 升级原因 | 平均披露字段数 | 直接泄露率 | Valid Output | 交易前拒绝率 |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 普通研究 | 无 | TBD | TBD | TBD | TBD | TBD | TBD |
| 风险分析 | 无 | TBD | TBD | TBD | TBD | TBD | TBD |
| 交易执行 | 无 | TBD | TBD | TBD | TBD | TBD | TBD |
| 重复披露 | 无 | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉任务阶段 | 阶段状态 | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉风险信号 | 风险状态 | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉历史记录 | 累计披露 | TBD | TBD | TBD | TBD | TBD | TBD |

### 表 A3：动态策略与开发集最优固定选择的差距

**问题：** 动态 Agent 在测试集上的选择，是否接近开发集上“满足效用要求时披露最少”的可计算参考。

先在固定开发集上确定每类任务的最低可接受等级，再锁定规则，在测试集上只评估动态方案。开发集不能使用测试结果重新调等级。

| 任务类别 | 开发集最低固定等级 | 测试集动态平均等级 | 等级差 | 测试集效用保持 | 测试集 ReID@1 | 测试集 Link AUC | 额外 Token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 研究 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 风险分析 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 组合管理 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 交易执行 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 总体 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## 第二组：长程替换与效用保持

### 表 B1：任务长度增加时的效用衰减

**问题：** 隐私处理或引用问题造成的损失，是否会随着任务从短期变成长程而累积。

从同一次完整运行中截取不同长度，不重新挑选日期；每个长度都从同一初始资金和状态开始计算。

| 方法 | 1 日效用保持 | 5 日效用保持 | 20 日效用保持 | 60 日效用保持 | 全年效用保持 | 全年 Valid | 全年执行中断 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 100% | 100% | 100% | 100% | 100% | TBD | TBD |
| 固定别名 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 按任务替换 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

效用保持以同一窗口 Vanilla 的累计收益为参照，同时保存 Return、Sharpe 和 MDD 原值。该表看的是随长度变化的曲线，不把某一天的动作是否相同当成成功标准。

### 表 B2：匿名轨迹增长时的攻击增强

**问题：** 攻击者看到更长的匿名历史后，是否更容易把不同日期的对象串起来或猜出真实证券。

主攻击器固定为无需训练的 Qwen3.5-4B，任务模型固定为 Qwen3.8-27B；`canonical_id` 和本地映射不进入攻击 Prompt。先验按 K1 候选集合、K2 静态主表、K3 公开行情和 K4 跨轮行为逐级增强；比较轨迹长度时固定 K4，只增加外部可见历史。

| 方法 | 1 日 ReID / Link | 5 日 ReID / Link | 20 日 ReID / Link | 60 日 ReID / Link | 全年 ReID / Link |
| --- | ---: | ---: | ---: | ---: | ---: |
| 固定别名 | TBD | TBD | TBD | TBD | TBD |
| 按任务替换 | TBD | TBD | TBD | TBD | TBD |
| 按日替换 | TBD | TBD | TBD | TBD | TBD |
| FinScope | TBD | TBD | TBD | TBD | TBD |

每个单元同时保存攻击候选数和随机基线；`Link AUC` 越接近 0.5 越好，不能只报告短窗口的随机猜测结果。

正式机器可读结果同时保存 ReID@5、MRR、Link AUPRC、TPR@1%FPR、coverage 和 95% CI。上述六项均为标准检索或验证指标；本项目新增的是从真实外发轨迹构造标签隔离的身份目标和同实体/异实体配对协议。旧 Jaccard/oracle 结果只作为弱攻击基线。

### 表 B3：替换更新周期敏感性

**问题：** 句柄多久更新一次，才能在任务内保持可用、在任务外减少关联，同时不产生过高成本。

只改变句柄生命周期，其余提示、模型、数据和执行器完全相同。

| 更新周期 | 同任务引用有效率 | 跨日 Link AUC | ReID@1 | 旧句柄拒绝率 | 效用保持 | Token 增量 | E2E p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 从不更新 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 每 20 个交易日 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 每 5 个交易日 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 每个交易日 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 每个任务 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| FinScope 当前策略 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## 第三组：主方法必要性

### 表 C1：本地隐私 Agent 模型选择

**问题：** 哪个不超过 4B 的本地模型足以承担识别、规划和审计，并且开销最低。

只在固定的 20 个开发交易日上运行；模型选定后，后续所有正式实验固定使用它，测试集不能反向选择。严格模式禁止整条链路静默退回确定性 Agent。

| 模型 | 参数量 | 严格规划合法率 | 识别失败率 | 审计失败率 | 整链回退次数 | 规划修正率 | 本地 Token | 本地 p95 | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3.5-0.8B | 0.8B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Qwen3.5-2B | 2B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Qwen3.5-4B | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Qwen3-0.6B | 0.6B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Qwen3-1.7B | 1.7B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Llama 3.2 1B 指令版 | 1B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Llama 3.2 3B 指令版 | 3B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Gemma 3 1B | 1B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Gemma 3 4B | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待跑 |
| Gemma 4 4B | 4B | TBD | TBD | TBD | TBD | TBD | TBD | TBD | 待核验 |

### 表 C2：FinScope 关键组件消融

**问题：** 主方法的效果是否来自各个具体组件，而不是单纯来自增加一个本地 Agent。

所有变体使用同一模型、数据和初始 P3；每行只删除一个组件。表中只报告组件直接影响的相对变化，不复制主表整套结果。

| 变体 | 删除组件 | 效用保持 | ReID@1 | Link AUC | 作用域/历史错误 | Unsafe Repair | 交易前中断 | 本地 p95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 完整 FinScope | 无 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉动态披露 | P1-P5 动态选择 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉历史记录 | 累计披露状态 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉任务内缓存 | 同一任务映射缓存 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉跨日轮换 | 任务/交易日轮换 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 去掉主表校验 | 证券事实校验 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## 实验与论文故事对应关系

| 实验 | 回答的问题 | 服务的故事 |
| --- | --- | --- |
| A1 | 动态披露是否比固定等级更好 | 隐私和任务效用不能用一个固定强度处理 |
| A2 | 动态选择是否真的读了场景 | 动态机制不是随机或固定规则 |
| A3 | 动态选择是否接近可达到的最低披露 | 动态策略不是凭感觉调参 |
| B1 | 长程任务的效用是否衰减 | 局部信息损失是否会累积成金融损失 |
| B2 | 长历史是否增强攻击 | 替换策略是否能抵抗轨迹拼接 |
| B3 | 更新周期如何影响折中 | 任务内稳定和跨日隐私之间如何取值 |
| C1 | 本地 Agent 应选哪个小模型 | 隐私 Agent 不需要复制 27B 任务模型 |
| C2 | 哪些组件真正有作用 | 方法效果是否有组件级因果解释 |

## 运行边界与当前状态

主实验的 Qwen27B 任务和外部矩阵正在运行，补充实验不抢占其 GPU，也不复用未完成的中间结果。C1 使用现有 `benchmarks/run_nlpcc_local_model_ablation.py`；当前 Gemma 4 4B 权重路径尚未核验，10 模型表在核验前不能标记完成。A1-A3 需要在 runner 中记录动态等级、触发原因和累计披露状态；B1-B3 使用同一次完整 NLPCC 轨迹按窗口重算，不需要重新请求任务模型；C2 使用已有 runner 的方法开关和故障注入结果。

正式结果填入前必须保留：数据版本、模型 revision、配置摘要、随机种子、开发/测试边界、逐日记录和运行日志。所有缺少真实执行反馈的指标保持 `TBD`，不使用模型 Judge，也不把旧 preliminary 数字写入这些表。
