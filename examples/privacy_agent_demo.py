"""Offline demo: no model server or external API is required."""

from finscope import DisclosureLevel, LocalPrivacyAgent


CATALOG = [
    {
        "canonical_id": "600519.SH",
        "name": "贵州茅台",
        "aliases": ["600519"],
        "asset_type": "股票",
        "market": "A股",
        "sector_l1": "消费",
        "sector_l2": "食品饮料",
        "sector_l3": "白酒",
        "size_bucket": "大盘",
    },
    {
        "canonical_id": "000858.SZ",
        "name": "五粮液",
        "aliases": ["000858"],
        "asset_type": "股票",
        "market": "A股",
        "sector_l1": "消费",
        "sector_l2": "食品饮料",
        "sector_l3": "白酒",
        "size_bucket": "大盘",
    },
]


agent = LocalPrivacyAgent(CATALOG, default_level=DisclosureLevel.P3)
scope = agent.open_scope("demo-rebalance", "2026-08-21")

safe = agent.sanitize(
    {"candidate_pool": ["贵州茅台", "五粮液"], "question": "比较两只股票"},
    scope,
    disclosure_level="P2",
)
print("发送给外部模型：", safe)

# 实际使用时这里是外部模型返回的 JSON。演示直接复用句柄。
first_ref = safe["candidate_pool"][0]
result = agent.restore_and_audit({"asset": first_ref, "reason": "基本面更稳健"}, scope)
print("本地恢复结果：", result.value)
print("审计状态：", result.status)

agent.close_scope(scope)
