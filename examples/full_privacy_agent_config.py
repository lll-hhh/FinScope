"""Full local-agent wiring example; requires a running Qwen endpoint."""

from finscope import (
    FinScopeMediator,
    JsonModelDisclosurePlanner,
    JsonModelEntityRecognizer,
    JsonModelRecoveryAuditor,
    LocalPrivacyAgent,
    OpenAICompatibleChatModel,
    local_qwen_profile,
)


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
        "version": "2026-08-21",
    }
]


# One local model client can serve three constrained roles. Each role has its
# own JSON prompt and code-side validation; none may mutate the identity table.
local_model = OpenAICompatibleChatModel(local_qwen_profile())
mediator = FinScopeMediator(
    CATALOG,
    entity_recognizer=JsonModelEntityRecognizer(local_model),
)
privacy_agent = LocalPrivacyAgent(
    CATALOG,
    mediator=mediator,
    disclosure_planner=JsonModelDisclosurePlanner(local_model),
    recovery_auditor=JsonModelRecoveryAuditor(local_model),
    default_level="P3",
)

scope = privacy_agent.open_scope("demo", "2026-08-21")
safe = privacy_agent.sanitize("研究贵州茅台并判断是否增持", scope)
print(safe)
