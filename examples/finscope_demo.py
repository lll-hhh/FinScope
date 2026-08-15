"""Minimal FinScope integration example.

Run from the repository root with ``python3 -m examples.finscope_demo``.
"""

from typing import Dict

from finscope import FinScopeMediator


def fake_external_llm(payload: Dict[str, str]) -> Dict[str, object]:
    # This function stands in for an OpenAI-compatible client.  It sees only
    # the scoped alias and returns an alias that is restored locally.
    print("External payload:", payload)
    alias = next(token for token in payload["prompt"].split() if token.startswith("FS_ASSET_"))
    return {"asset": alias, "side": "buy", "quantity": 10}


def main() -> None:
    mediator = FinScopeMediator(
        [{"name": "Apple Inc.", "aliases": ["AAPL"]}]
    )
    scope = mediator.open_scope("demo-research-and-trade", "2026-08-14")
    response = mediator.call_external(
        {"prompt": "分析 AAPL 的短期交易机会"}, fake_external_llm, scope
    )
    print("Local response:", response)
    print("Validated action:", mediator.validate_action(response, scope).action)
    mediator.close_scope(scope)


if __name__ == "__main__":
    main()
