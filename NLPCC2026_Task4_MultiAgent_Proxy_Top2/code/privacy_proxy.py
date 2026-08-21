#!/usr/bin/env python3
"""OpenAI-compatible privacy proxy for NLPCC 2026 Shared Task 4.

The official starter agent can point ``OPENAI_API_BASE`` at this service.  The
proxy forwards requests to a local OpenAI-compatible model server and exposes
three controlled conditions without changing the official agent code:

``original``
    Forward the prompt unchanged.
``direct``
    Apply one global deterministic name/code mapping for the complete run.
``finscope``
    Apply FinScope's task/day scoped mapping and restore the response locally.

Every request produces one JSONL audit record containing role, date, latency,
character counts, alias counts, and FinScope counters.  Prompts and model
responses are deliberately not written to the audit log.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from finscope import FinScopeMediator, PrivacyLevel, Scope


DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})(?:日)?(?!\d)")
DEFAULT_DAY = "2025-01-02"


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_strings(item)


def _extract_day(payload: Mapping[str, Any], fallback: str) -> str:
    candidates: list[str] = []
    for text in _walk_strings(payload.get("messages", [])):
        for match in DATE_PATTERN.finditer(text):
            year, month, day = (int(part) for part in match.groups())
            candidates.append(f"{year:04d}-{month:02d}-{day:02d}")
    # Prompts often include historical observations before saying "today".
    # The latest visible date is the safest deterministic proxy for the current
    # decision day and never introduces future information.
    return max(candidates) if candidates else fallback


def _classify_role(payload: Mapping[str, Any]) -> str:
    text = "\n".join(_walk_strings(payload.get("messages", [])))
    # Match the most downstream/specific role first: the trading prompt embeds
    # sentiment and news summaries, so broad keyword checks would otherwise
    # misclassify it and prevent the end-of-cycle scope rotation.
    if "日频率量化交易员" in text or ("当前持仓" in text and '"trades"' in text):
        return "trading"
    if "金融市场舆情分析师" in text or "overall_sentiment" in text:
        return "sentiment"
    if "请将以下金融新闻提取" in text or (
        "金融新闻" in text and "只返回摘要内容" in text
    ):
        return "news"
    return "unknown"


def _char_count(value: Any) -> int:
    return sum(len(text) for text in _walk_strings(value))


def _load_catalog(nlpcc_root: Path) -> list[dict[str, Any]]:
    sys.path.insert(0, str(nlpcc_root))
    try:
        from agent_platform.agents.fund_info import FUND_INFO  # type: ignore
    finally:
        sys.path.pop(0)
    # The official executor accepts exchange-qualified security codes only.
    # Therefore the executable code must be FinScope's canonical restore value,
    # while the human-readable Chinese fund name is merely another surface form
    # that receives the same privacy alias.  Reversing these two fields would
    # produce fluent model output that the backtester cannot execute.
    return [
        {"name": code, "aliases": [details["name"]]}
        for code, details in sorted(FUND_INFO.items())
    ]


def _load_trading_days(nlpcc_root: Path) -> tuple[str, ...]:
    price_dir = nlpcc_root / "dataset" / "price_data" / "export_data"
    price_file = next(iter(sorted(price_dir.glob("*.csv"))), None)
    if price_file is None:
        return ()
    days: set[str] = set()
    with price_file.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = str(row.get("date", "")).strip()
            if re.fullmatch(r"20\d{6}", raw):
                days.add(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
    return tuple(sorted(days))


class DirectMapper:
    """A deliberately simple, globally stable mapping baseline."""

    def __init__(self, catalog: Sequence[Mapping[str, Any]]) -> None:
        pairs: list[tuple[str, str]] = []
        reverse: dict[str, str] = {}
        for index, entry in enumerate(catalog, start=1):
            canonical = str(entry["name"])
            alias = f"DM_ASSET_{index:04d}"
            reverse[alias] = canonical
            pairs.append((canonical, alias))
            for surface in entry.get("aliases", []):
                pairs.append((str(surface), alias))
        self._pairs = sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)
        self._reverse = reverse

    @staticmethod
    def _surface_pattern(surface: str) -> str:
        if surface and surface[0].isascii() and surface[-1].isascii():
            return rf"(?<![A-Za-z0-9_]){re.escape(surface)}(?![A-Za-z0-9_])"
        return re.escape(surface)

    @staticmethod
    def _replace_text(text: str, pairs: Sequence[tuple[str, str]]) -> str:
        result = text
        for surface, replacement in pairs:
            pattern = DirectMapper._surface_pattern(surface)
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    def count_raw(self, value: Any) -> int:
        surfaces = {surface for surface, _ in self._pairs if surface}
        return sum(
            len(re.findall(self._surface_pattern(surface), text, flags=re.IGNORECASE))
            for text in _walk_strings(value)
            for surface in surfaces
        )

    def sanitize(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._replace_text(value, self._pairs)
        if isinstance(value, Mapping):
            return {key: self.sanitize(item) for key, item in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.sanitize(item) for item in value]
        return value

    def restore(self, value: Any) -> Any:
        pairs = tuple(self._reverse.items())
        if isinstance(value, str):
            return self._replace_text(value, pairs)
        if isinstance(value, Mapping):
            return {key: self.restore(item) for key, item in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.restore(item) for item in value]
        return value


@dataclass
class ProxyConfig:
    mode: str
    upstream_url: str
    upstream_model: str
    task_id: str
    conversation_id: str
    default_day: str
    trading_days: tuple[str, ...]
    audit_log: Path


class PrivacyController:
    def __init__(self, config: ProxyConfig, catalog: Sequence[Mapping[str, Any]]) -> None:
        self.config = config
        self.direct = DirectMapper(catalog)
        self.mediator = FinScopeMediator(catalog)
        self._scope: Scope | None = None
        self._scope_cursor: int | None = None
        self._rotate_after_trade = False
        self._audit_lock = asyncio.Lock()
        self._request_id = 0
        config.audit_log.parent.mkdir(parents=True, exist_ok=True)

    def _next_scope_day(self) -> str:
        if self.config.trading_days:
            if self._scope_cursor is None:
                try:
                    self._scope_cursor = self.config.trading_days.index(self.config.default_day)
                except ValueError:
                    self._scope_cursor = 0
            else:
                self._scope_cursor = min(self._scope_cursor + 1, len(self.config.trading_days) - 1)
            return self.config.trading_days[self._scope_cursor]
        base = datetime.strptime(self.config.default_day, "%Y-%m-%d").date()
        offset = 0 if self._scope_cursor is None else self._scope_cursor + 1
        self._scope_cursor = offset
        return (base + timedelta(days=offset)).isoformat()

    def transform_request(
        self,
        payload: Dict[str, Any],
        observed_day: str,
        role: str,
    ) -> tuple[Dict[str, Any], Scope | None]:
        outbound = dict(payload)
        outbound["model"] = self.config.upstream_model
        if self.config.mode == "original":
            return outbound, None
        if self.config.mode == "direct":
            return self.direct.sanitize(outbound), None
        # One FinScope scope covers a complete multi-agent decision cycle:
        # concurrent news workers -> sentiment agent -> trading agent.  Dates
        # found inside news text are article dates (and may even be future dates
        # mentioned by an article), so they must not drive lifecycle rotation.
        # The next trading-day scope is opened only after the trading response
        # has been restored locally.
        if self._scope is None or self._rotate_after_trade:
            self._scope = self.mediator.open_scope(
                self.config.task_id,
                self._next_scope_day(),
                conversation_id=self.config.conversation_id,
                privacy_level=PrivacyLevel.STANDARD,
            )
            self._rotate_after_trade = False
        return self.mediator.sanitize(outbound, self._scope), self._scope

    def restore_response(
        self,
        payload: Dict[str, Any],
        scope: Scope | None,
        role: str,
    ) -> Dict[str, Any]:
        if self.config.mode == "original":
            return payload
        if self.config.mode == "direct":
            restored = self.direct.restore(payload)
        else:
            if scope is None:
                raise RuntimeError("FinScope response is missing its scope")
            restored = self.mediator.restore_output(payload, scope)
            if role == "trading" and self._scope is not None and scope.id == self._scope.id:
                self._rotate_after_trade = True
        if not isinstance(restored, dict):
            raise TypeError("restored OpenAI response must be an object")
        return restored

    async def audit(self, record: MutableMapping[str, Any]) -> None:
        async with self._audit_lock:
            self._request_id += 1
            record["request_id"] = self._request_id
            with self.config.audit_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def create_app(config: ProxyConfig, catalog: Sequence[Mapping[str, Any]]) -> FastAPI:
    controller = PrivacyController(config, catalog)
    app = FastAPI(title="FinScope NLPCC privacy proxy")

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "mode": config.mode, "upstream": config.upstream_url}

    @app.get("/v1/models")
    async def models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": config.upstream_model, "object": "model", "owned_by": "local"}],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> JSONResponse:
        payload = await request.json()
        if payload.get("stream"):
            raise HTTPException(status_code=400, detail="streaming is not supported by this experiment proxy")
        day = _extract_day(payload, config.default_day)
        role = _classify_role(payload)
        input_chars = _char_count(payload.get("messages", []))
        input_sensitive = controller.direct.count_raw(payload.get("messages", []))
        outbound, scope = controller.transform_request(payload, day, role)
        outbound_chars = _char_count(outbound.get("messages", []))
        outbound_sensitive = controller.direct.count_raw(outbound.get("messages", []))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    config.upstream_url.rstrip("/") + "/chat/completions",
                    json=outbound,
                    headers={"Authorization": "Bearer local"},
                )
            response.raise_for_status()
            upstream_payload = response.json()
            restored = controller.restore_response(upstream_payload, scope, role)
            status = "ok"
        except Exception as exc:
            await controller.audit(
                {
                    "timestamp": time.time(),
                    "mode": config.mode,
                    "day": day,
                    "role": role,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "latency_s": time.perf_counter() - started,
                    "input_chars": input_chars,
                    "outbound_chars": outbound_chars,
                    "input_sensitive_occurrences": input_sensitive,
                    "outbound_sensitive_occurrences": outbound_sensitive,
                }
            )
            raise HTTPException(status_code=502, detail=f"upstream model request failed: {type(exc).__name__}") from exc

        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "mode": config.mode,
            "day": day,
            "role": role,
            "status": status,
            "latency_s": time.perf_counter() - started,
            "input_chars": input_chars,
            "outbound_chars": outbound_chars,
            "input_sensitive_occurrences": input_sensitive,
            "outbound_sensitive_occurrences": outbound_sensitive,
            "output_chars": _char_count(restored),
            "alias_occurrences": sum(
                text.count("FS_ASSET_") if config.mode == "finscope" else text.count("DM_ASSET_")
                for text in _walk_strings(outbound.get("messages", []))
            ),
            "usage": upstream_payload.get("usage", {}),
        }
        if scope is not None:
            record["scope_day"] = scope.trading_day
            record["finscope_metrics"] = controller.mediator.get_metrics(scope)
            record["privacy_status"] = controller.mediator.get_privacy_status(scope)
        await controller.audit(record)
        return JSONResponse(restored)

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["original", "direct", "finscope"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--upstream-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--nlpcc-root", type=Path, required=True)
    parser.add_argument("--task-id", default="nlpcc2026-task4")
    parser.add_argument("--conversation-id", default="news-sentiment-trading")
    parser.add_argument("--default-day", default=DEFAULT_DAY)
    parser.add_argument("--audit-log", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ProxyConfig(
        mode=args.mode,
        upstream_url=args.upstream_url,
        upstream_model=args.upstream_model,
        task_id=args.task_id,
        conversation_id=args.conversation_id,
        default_day=args.default_day,
        trading_days=_load_trading_days(args.nlpcc_root),
        audit_log=args.audit_log,
    )
    catalog = _load_catalog(args.nlpcc_root)
    app = create_app(config, catalog)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
