# FinScope 最小实现

`finscope/` 是一个基础运行无第三方依赖的本地隐私 Agent。它不实现具体的金融策略，也不要求重写 Agent，只包住外部 LLM 客户端和本地工具执行器。

新代码优先使用 `LocalPrivacyAgent`。底层 `FinScopeMediator` 负责实体发现、作用域映射和确定性恢复；上层隐私 Agent 再增加 P1-P5 语义披露、typed handle 和恢复歧义审计。

```python
from finscope import LocalPrivacyAgent

agent = LocalPrivacyAgent(local_security_master, default_level="P3")
scope = agent.open_scope("task-1", "2026-08-21")
safe = agent.sanitize(raw_prompt, scope, disclosure_level="P2")
result = agent.restore_and_audit(external_llm(safe), scope)
```

外部文本形如 `<fin-ref type="asset" id="FS_ASSET_...">白酒股票</fin-ref>`。描述保留可控语义，句柄保证同类资产仍可唯一恢复。交易入口使用 `agent.validate_action(...)`；句柄缺失、过期或绑定冲突时默认拒绝执行。

## 实现流程

每次 `sanitize` 都执行两阶段处理：

1. 本地 security master、结构化字段规则和当前作用域已有映射先替换已知资产、持仓、账户等内容；
2. 本地小模型只读取这份已经替换的残余文本，识别新出现的实体、代词/指代、动作动词、关系和意图，并返回原文片段、类型、风险等级以及可选的 `refers_to`；
3. FinScope 校验片段确实存在于模型输入中，过滤模型输出的 `FS_*` 假实体，并在本地为新语义分配代号；
4. 按 span 从后往前替换，之后对没有歧义的同义词再做一次补漏替换。

### 小模型调用门控

小模型不是每条消息都调用。`ResidualScanPolicy` 默认先预热两次，连续三次没有新替换后进入 cooldown；命中已确认安全的模板直接跳过，连续跳过十次做一次真实周期抽检。抽检会清除识别器缓存，保证重新喂给模型。未识别的 Ticker/六位证券代码、账户/持仓/调仓词、保密等级上升和显式 `force_model_scan=True` 都会立即唤醒模型。默认是 `balanced`，高风险实验可以配置 `mode="conservative"`，对每个新模板都扫描。

```python
from finscope import ResidualScanPolicy

mediator = FinScopeMediator(
    asset_catalog,
    entity_recognizer=local_recognizer,
    residual_scan_policy=ResidualScanPolicy(
        warmup_scans=2,
        no_new_threshold=3,
        probe_interval=10,
        mode="balanced",
    ),
)

# Feed a newly refreshed news/tool source through a fresh local scan.
safe = mediator.sanitize_tool_result(
    news_result,
    scope,
    force_model_scan=True,
)
print(mediator.get_privacy_status(scope))
```

`get_metrics(scope)` 会记录 `recognizer_calls`、`recognizer_skips`、`recognizer_probes`、`recognizer_empty_scans` 和 `recognizer_new_replacements`，可以直接换算本地模型调用节省比例。

模型不能创建代号或修改映射表。`reference` 如果指向已有 alias，会直接复用目标 alias；因此“该股”“它”等指代不会平白产生第二个代号。相同表面词如果同时代表资产和机构，FinScope 保留多个 typed mapping，只有模型给出具体 span/type 时才替换，避免全局字符串替换误伤。

```python
from finscope import FinScopeMediator

mediator = FinScopeMediator([
    {"name": "Apple Inc.", "aliases": ["AAPL"]},
    {"name": "Microsoft Corporation", "aliases": ["MSFT"]},
])
scope = mediator.open_scope(
    "rebalance-42",
    "2026-08-14",
    conversation_id="research-risk-trading",
)

# Research/Risk/Trading agents all receive the same scope handle.
safe_messages = mediator.sanitize_messages(messages, scope)
safe_tool_result = mediator.sanitize_tool_result(local_tool_result, scope)
model_output = external_llm(safe_messages)
local_output = mediator.restore_output(model_output, scope)
action = mediator.validate_action(local_output, scope).action
local_executor.execute(action)

# At task end, erase the mapping. Opening the same task on a new trading day
# also rotates it automatically.
mediator.close_scope(scope)
```

也可以使用 `with mediator.task_scope(...) as scope:`，在任务退出时自动清理映射。资产目录在本地把正式名称、Ticker、ISIN 等同义标识绑定到同一个 canonical 资产；研究、风控和交易 Agent 必须共享同一个 `scope`。

第一版保留数量、价格和权重数值，映射资产、机构、组合、策略和账户身份；这样可以先验证任务效用和工具调用闭环。动作、关系和意图默认在高保密等级或模型标为高风险时才替换，避免低风险研究任务丢失金融语义。

## 动态保密等级和生命周期

作用域可以用 `LOW`、`STANDARD`、`HIGH` 或 `CRITICAL` 初始化。策略会在会话内单调升级：出现 holdings/positions、候选池和权重时至少升到 `HIGH`；出现 orders/trades/account 或执行字段时升到 `CRITICAL`；检测到提示注入/索要映射表的标记，或多次累计外发，也会升级。等级不会在同一会话内自动降低，降低保护强度必须打开新 conversation scope。

代号的稳定范围是 `(task_id, conversation_id, trading_day)`：研究、风控、交易 Agent 共享同一个 scope；新 conversation、任务结束 `close_scope`、或交易日变化都会清空双向表并重新随机生成代号。这样既不会在一次流程内混淆，也不会让外部模型跨会话和跨日关联轨迹。

```python
mediator.set_privacy_level(scope, "HIGH")
print(mediator.get_privacy_status(scope))
print(mediator.get_mapping_records(scope))  # local trusted evaluator only
```

## 本地小模型识别

敏感信息识别不依赖外部大模型。推荐先用 `Qwen3-0.6B`，关闭 thinking，让它只输出原始文本片段及类型：

```json
{"entities": [{"text": "AAPL", "type": "asset", "canonical": null}]}
```

模型支持识别 `asset`、`institution`、`portfolio`、`strategy`、`account`、`reference`、`action`、`relation` 和 `intent`。它不能创建 alias，也不能修改映射表。FinScope 会验证片段确实存在于模型输入，资产再用本地证券主表校验，然后分别创建 `FS_ASSET_*`、`FS_ORG_*`、`FS_PORTFOLIO_*`、`FS_STRATEGY_*`、`FS_ACCOUNT_*`、`FS_ACTION_*` 等 typed aliases。输出恢复是本地字典替换，不再调用模型；恢复支持 JSON 字段、反引号、括号、所有格和中英文标点前后缀。若模型输出非法 JSON 或漏掉证券主表中的资产，系统保留第一阶段的确定性结果。

```python
from finscope import FinScopeMediator

mediator = FinScopeMediator.from_local_model(
    "/path/to/Qwen3-0.6B",
    asset_catalog=local_security_master,
    device="cuda:0",
)
scope = mediator.open_scope("rebalance-42", "2026-08-15")
safe_prompt = mediator.sanitize_prompt(raw_prompt, scope)
restored = mediator.restore_output(external_llm(safe_prompt), scope)
```

如果外部返回交易字段 `{"asset": "FS_ASSET_xxxxxxxx's", "side": "buy"}`，本地执行边界会识别带所有格后缀的唯一 alias，恢复成真实资产后再做资产注册、订单方向、数量、价格和权重校验。

同一个 scope 由研究、风控和交易 Agent 共享，因此任务内代号一致；任务结束调用 `close_scope`，或同一任务切换交易日时，内存映射会被清除并重新随机生成。映射表形如 `{FS_ASSET_xxxxxxxx: 贵州茅台}`，只允许本地恢复器和评测代码读取。

实验代码可以通过 `get_local_mapping(scope)` 在本地读取映射快照，用于构造重识别攻击的 ground truth；这个快照不能写入外部模型日志。

示例见 `examples/finscope_local_model_demo.py`。Qwen3 需要较新的 `transformers`；运行前应在独立本地推理环境安装兼容版本的 `torch` 和 `transformers`。
