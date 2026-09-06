"""OpenAI-compatible privacy proxy for StockBench and FinVault experiments."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from finscope import (
    AdaptiveReplacementController,
    AdaptiveRuntime,
    LocalPrivacyAgent,
    RiskEstimator,
    TaskDependencyState,
    load_risk_estimator,
)
from benchmarks.local_privacy_agent import (
    LocalPrivacyModelConfig,
    build_model_assisted_agent,
    usage_delta,
)


METHODS = (
    "vanilla",
    "deletion",
    "llm_rewrite",
    "global_alias",
    "episode_alias",
    "finscope",
)

DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"PERSON|ORGANIZATION|LOCATION|CUSTOMER|ACCOUNT|ASSET|CASE-REF|SWIFT|"
    r"POLICY|DOCUMENT|EMPLOYEE|USER|PRODUCT|APPLICATION|LOAN|ALERT|ORDER|"
    r"TRANSACTION|PORTFOLIO|STRATEGY|CONTRACT|CLAIM|MERCHANT|DEVICE"
    r"|PHONE|EMAIL|LICENSE|FACILITY|URL|BRAND|COMPANY"
    r")[A-Z0-9_-]*\d[A-Z0-9_-]*(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
PUBLIC_ASSET_PATTERN = re.compile(
    r"^(?:[036]\d{5}|[A-Z]{1,5})$"
)
PUBLIC_IDENTIFIER_FIELDS = {
    "stock_code": ("financial asset", "listed financial asset"),
    "stock_symbol": ("financial asset", "listed financial asset"),
    "ticker": ("financial asset", "listed financial asset"),
    "symbol": ("financial asset", "listed financial asset"),
    "asset_code": ("financial asset", "listed financial asset"),
    "fund_code": ("financial asset", "listed financial asset"),
    "target_company": ("financial asset", "listed financial asset"),
    "currency": ("financial asset", "currency identifier"),
    "pledged_to": ("organization identifier", "organization identifier"),
    "sender_country": ("location identifier", "location identifier"),
    "receiver_country": ("location identifier", "location identifier"),
}
ALIAS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:GA|EA)_[A-Z]+_[A-F0-9]{10}(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
REWRITE_MAX_TOKENS = 1024


STOCK_PROFILES: Mapping[str, Tuple[str, str, str]] = {
    "GS": ("Goldman Sachs", "Financials", "investment bank stock"),
    "MSFT": ("Microsoft", "Technology", "software stock"),
    "HD": ("Home Depot", "Consumer", "home improvement retail stock"),
    "V": ("Visa", "Financials", "payment network stock"),
    "SHW": ("Sherwin-Williams", "Materials", "coatings stock"),
    "CAT": ("Caterpillar", "Industrials", "industrial machinery stock"),
    "MCD": ("McDonald's", "Consumer", "restaurant stock"),
    "UNH": ("UnitedHealth", "Health Care", "managed care stock"),
    "AXP": ("American Express", "Financials", "consumer finance stock"),
    "AMGN": ("Amgen", "Health Care", "biotechnology stock"),
    "TRV": ("Travelers", "Financials", "insurance stock"),
    "CRM": ("Salesforce", "Technology", "enterprise software stock"),
    "JPM": ("JPMorgan Chase", "Financials", "diversified bank stock"),
    "IBM": ("IBM", "Technology", "IT services stock"),
    "HON": ("Honeywell", "Industrials", "industrial conglomerate stock"),
    "BA": ("Boeing", "Industrials", "aerospace stock"),
    "AMZN": ("Amazon", "Consumer", "e-commerce stock"),
    "AAPL": ("Apple", "Technology", "consumer technology stock"),
    "PG": ("Procter & Gamble", "Consumer", "consumer staples stock"),
    "JNJ": ("Johnson & Johnson", "Health Care", "health care stock"),
}


@dataclass(frozen=True)
class CatalogEntry:
    canonical_id: str
    name: str
    aliases: Tuple[str, ...]
    entity_type: str
    descriptor: str
    sector: str = ""

    def surfaces(self) -> Tuple[str, ...]:
        values = (self.canonical_id, self.name) + self.aliases
        return tuple(dict.fromkeys(value for value in values if value))

    def as_finscope(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            # FinScopeMediator restores to ``name``. Keep the executable
            # benchmark identifier there and treat display names as aliases.
            "name": self.canonical_id,
            "aliases": list(dict.fromkeys((self.name,) + self.aliases)),
            "asset_type": self.entity_type,
            "market": "public benchmark",
            "sector_l1": self.sector or self.entity_type,
            "sector_l2": self.descriptor,
            "sector_l3": self.descriptor,
            "size_bucket": "standard",
            "version": "external-benchmark-v1",
        }


def stockbench_catalog() -> List[CatalogEntry]:
    aliases = {
        "GS": ("Goldman Sachs Group",),
        "MSFT": ("Microsoft Corp", "Microsoft Corporation"),
        "HD": ("The Home Depot",),
        "V": ("Visa Inc",),
        "SHW": ("Sherwin Williams",),
        "CAT": ("Caterpillar Inc",),
        "MCD": ("McDonalds",),
        "UNH": ("UnitedHealth Group",),
        "AXP": ("American Express Company",),
        "AMGN": ("Amgen Inc",),
        "TRV": ("The Travelers Companies",),
        "CRM": ("Salesforce Inc",),
        "JPM": ("JPMorgan",),
        "IBM": ("International Business Machines",),
        "HON": ("Honeywell International",),
        "BA": ("The Boeing Company",),
        "AMZN": ("Amazon.com",),
        "AAPL": ("Apple Inc",),
        "PG": ("Procter and Gamble",),
        "JNJ": ("Johnson and Johnson",),
    }
    return [
        CatalogEntry(symbol, name, aliases.get(symbol, ()), "stock", descriptor, sector)
        for symbol, (name, sector, descriptor) in STOCK_PROFILES.items()
    ]


def _entity_type(token: str) -> str:
    prefix = token.upper().split("-", 1)[0].split("_", 1)[0]
    return {
        "PERSON": "person identifier",
        "ORGANIZATION": "organization identifier",
        "LOCATION": "location identifier",
        "CUSTOMER": "customer identifier",
        "ACCOUNT": "account identifier",
        "ASSET": "financial asset",
        "POLICY": "policy identifier",
        "DOCUMENT": "document identifier",
        "EMPLOYEE": "employee identifier",
        "USER": "user identifier",
        "PRODUCT": "financial product",
        "APPLICATION": "application identifier",
        "LOAN": "loan identifier",
        "ALERT": "alert identifier",
        "ORDER": "order identifier",
        "TRANSACTION": "transaction identifier",
        "PORTFOLIO": "portfolio identifier",
        "STRATEGY": "strategy identifier",
        "CONTRACT": "contract identifier",
        "CLAIM": "claim identifier",
        "MERCHANT": "merchant identifier",
        "DEVICE": "device identifier",
        "PHONE": "phone identifier",
        "EMAIL": "email identifier",
        "LICENSE": "license identifier",
        "FACILITY": "facility identifier",
        "URL": "URL identifier",
        "BRAND": "brand identifier",
        "COMPANY": "company identifier",
        "CASE": "case identifier",
        "SWIFT": "financial reference",
    }.get(prefix, "benchmark identifier")


def finvault_catalog(root: Path) -> List[CatalogEntry]:
    tokens: set[str] = set()
    public_identifiers: Dict[str, Tuple[str, str]] = {}

    def collect_public_assets(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().casefold()
                if normalized in PUBLIC_IDENTIFIER_FIELDS and isinstance(item, str):
                    candidate = item.strip().upper()
                    if PUBLIC_ASSET_PATTERN.fullmatch(candidate):
                        public_identifiers[candidate] = PUBLIC_IDENTIFIER_FIELDS[normalized]
                collect_public_assets(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                collect_public_assets(item)

    for directory in ("attack_datasets", "normal_datasets", "attack_datasets_synthesis"):
        base = root / "sandbox" / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*.json"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            tokens.update(match.group(0) for match in TOKEN_PATTERN.finditer(text))
            try:
                collect_public_assets(json.loads(text))
            except json.JSONDecodeError:
                continue
    entries = [
        CatalogEntry(token, token, (), _entity_type(token), _entity_type(token))
        for token in sorted(tokens, key=lambda value: (value.casefold(), value))
    ]
    entries.extend(
        CatalogEntry(identifier, identifier, (), entity_type, descriptor)
        for identifier, (entity_type, descriptor) in sorted(public_identifiers.items())
        if identifier not in tokens
    )
    return entries


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _walk_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_strings(item)


def _transform(value: Any, function) -> Any:
    if isinstance(value, str):
        return function(value)
    if isinstance(value, Mapping):
        return {
            function(key) if isinstance(key, str) else key: _transform(item, function)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_transform(item, function) for item in value]
    return value


_DECISION_FIELDS = frozenset(
    {
        "asset",
        "asset_code",
        "asset_name",
        "amount",
        "instrument",
        "market",
        "notional",
        "order_side",
        "percentage",
        "price",
        "quantity",
        "qty",
        "shares",
        "side",
        "symbol",
        "ticker",
        "tool",
        "venue",
        "weight",
    }
)


def _decision_projection(value: Any) -> Optional[Dict[str, Any]]:
    """Extract only executable decision fields from a local response."""

    if isinstance(value, Mapping):
        keys = {str(key).casefold() for key in value}
        if keys & _DECISION_FIELDS:
            return {
                str(key).casefold(): value[key]
                for key in value
                if str(key).casefold() in _DECISION_FIELDS
            }
        for key in (
            "choices",
            "message",
            "tool_calls",
            "function",
            "arguments",
            "content",
            "output",
            "result",
        ):
            if key in value:
                found = _decision_projection(value[key])
                if found is not None:
                    return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            found = _decision_projection(item)
            if found is not None:
                return found
    elif isinstance(value, str):
        candidate = value.strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return _decision_projection(parsed)
    return None


def _decision_fingerprint(value: Any) -> Optional[str]:
    projection = _decision_projection(value)
    if projection is None:
        return None
    encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _external_response_view(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep only response content that the external model provider can observe."""

    return {
        "choices": value.get("choices", []),
        "model": value.get("model"),
    }


class IdentityCatalog:
    def __init__(self, entries: Sequence[CatalogEntry]) -> None:
        self.entries = tuple(entries)
        pairs: List[Tuple[str, CatalogEntry]] = []
        for entry in entries:
            pairs.extend((surface, entry) for surface in entry.surfaces())
        self.pairs = tuple(sorted(pairs, key=lambda item: len(item[0]), reverse=True))

    @staticmethod
    def _pattern(surface: str) -> re.Pattern[str]:
        if surface and surface[0].isascii() and surface[-1].isascii():
            return re.compile(
                r"(?<![A-Za-z0-9_])" + re.escape(surface) + r"(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
        return re.compile(re.escape(surface), re.IGNORECASE)

    def replace(self, value: Any, replacements: Mapping[str, str]) -> Any:
        def replace_text(text: str) -> str:
            result = text
            for surface, entry in self.pairs:
                replacement = replacements.get(entry.canonical_id)
                if replacement is not None:
                    result = self._pattern(surface).sub(replacement, result)
            return result

        return _transform(value, replace_text)

    def count(self, value: Any) -> int:
        return sum(
            len(self._pattern(surface).findall(text))
            for text in _walk_strings(value)
            for surface, _ in self.pairs
        )


class AliasMapper:
    def __init__(
        self,
        catalog: IdentityCatalog,
        prefix: str,
        secret: bytes,
        episode: str,
    ) -> None:
        self.catalog = catalog
        self.forward: Dict[str, str] = {}
        for entry in catalog.entries:
            digest = hmac.new(
                secret,
                (episode + "\0" + entry.canonical_id).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()[:10].upper()
            type_name = re.sub(r"[^A-Z]", "", entry.entity_type.upper())[:12] or "ID"
            self.forward[entry.canonical_id] = f"{prefix}_{type_name}_{digest}"
        self.reverse = {alias: canonical for canonical, alias in self.forward.items()}

    def sanitize(self, value: Any) -> Any:
        return self.catalog.replace(value, self.forward)

    def restore(self, value: Any) -> Any:
        def restore_text(text: str) -> str:
            return ALIAS_PATTERN.sub(
                lambda match: self.reverse.get(match.group(0).upper(), match.group(0)),
                text,
            )

        return _transform(value, restore_text)

    def bindings(self) -> List[Dict[str, str]]:
        by_id = {entry.canonical_id: entry for entry in self.catalog.entries}
        return [
            {
                "canonical_id": canonical,
                "alias": alias,
                "descriptor": by_id[canonical].descriptor,
                "entity_type": by_id[canonical].entity_type,
            }
            for canonical, alias in self.forward.items()
        ]


@dataclass(frozen=True)
class ProxyConfig:
    benchmark: str
    method: str
    upstream_url: str
    upstream_model: str
    audit_log: Path
    disclosure_level: str
    seed: str
    timeout: float
    privacy_model_base_url: str = ""
    privacy_model_name: str = "Qwen2.5-3B-Instruct"
    adaptive_threshold: float = 0.60
    adaptive_calibration: str = ""


class PrivacyController:
    def __init__(self, config: ProxyConfig, entries: Sequence[CatalogEntry]) -> None:
        self.config = config
        self.catalog = IdentityCatalog(entries)
        self.secret = hashlib.sha256(config.seed.encode("utf-8")).digest()
        self.global_mapper = AliasMapper(self.catalog, "GA", self.secret, "global")
        self.episode_mappers: Dict[str, AliasMapper] = {}
        self.agents: Dict[str, LocalPrivacyAgent] = {}
        self.scopes: Dict[str, Any] = {}
        self.adaptive_controllers: Dict[str, AdaptiveReplacementController] = {}
        self.adaptive_runtimes: Dict[str, AdaptiveRuntime] = {}
        self.adaptive_context: Dict[str, Dict[str, Any]] = {}
        self.first_days: Dict[str, date] = {}
        self.lock = threading.RLock()
        self.audit_lock = threading.Lock()
        self.request_count = 0
        self.privacy_bundle = (
            build_model_assisted_agent(
                [entry.as_finscope() for entry in self.catalog.entries],
                LocalPrivacyModelConfig(
                    name="local-qwen-privacy-agent",
                    base_url=config.privacy_model_base_url,
                    model=config.privacy_model_name,
                    default_level=config.disclosure_level,
                ),
            )
            if config.method == "finscope" and config.privacy_model_base_url
            else None
        )
        self.risk_estimator = self._load_risk_estimator(config.adaptive_calibration)
        config.audit_log.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_risk_estimator(path: str) -> RiskEstimator:
        if not path:
            return RiskEstimator()
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError("adaptive calibration artifact not found: %s" % source)
        return load_risk_estimator(source)

    def episode_id(self, payload: Mapping[str, Any]) -> str:
        # FinScope keeps one task/session state across dates. Baselines retain
        # their day-scoped identifiers for an apples-to-apples comparison.
        task = payload.get("finscope_task")
        if self.config.method == "finscope" and isinstance(task, str) and task.strip():
            return task.strip()
        explicit = payload.get("finscope_episode")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        messages = payload.get("messages", [])
        texts = list(_walk_strings(messages))
        if self.config.benchmark == "stockbench":
            dates = [
                "%04d-%02d-%02d" % tuple(int(part) for part in match.groups())
                for text in texts
                for match in DATE_PATTERN.finditer(text)
            ]
            return max(dates) if dates else "stockbench-undated"
        first_user = ""
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, Mapping) and message.get("role") == "user":
                    first_user = "\n".join(_walk_strings(message.get("content", "")))
                    break
        source = first_user or "\n".join(texts)
        return "case-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    def trading_day(self, payload: Mapping[str, Any], episode: str) -> str:
        explicit = payload.get("finscope_episode")
        if isinstance(explicit, str) and DATE_PATTERN.fullmatch(explicit.strip()):
            return explicit.strip().replace("/", "-")
        texts = list(_walk_strings(payload.get("messages", [])))
        dates = [
            "%04d-%02d-%02d" % tuple(int(part) for part in match.groups())
            for text in texts
            for match in DATE_PATTERN.finditer(text)
        ]
        return max(dates) if dates else (episode if DATE_PATTERN.fullmatch(episode) else "2026-08-22")

    @staticmethod
    def task_phase(role: str, payload: Mapping[str, Any]) -> str:
        text = "\n".join(_walk_strings(payload.get("messages", []))).casefold()
        # StockBench supplies stable logical roles. Their system prompts
        # mention buy/sell even during research, so role takes precedence over
        # keyword matching to avoid forcing every request to P5.
        if role in {"fundamental_filter", "research_agent"}:
            return "analysis"
        if role in {"decision_agent", "portfolio_strategist"}:
            return "risk"
        if any(token in text for token in ("execute", "execution", "place order", "buy", "sell", "trade", "order")):
            return "execution"
        if "<decision>" in text:
            return "risk"
        return "tool"

    @staticmethod
    def field_risk(phase: str, payload: Mapping[str, Any]) -> int:
        text = "\n".join(_walk_strings(payload.get("messages", []))).casefold()
        if phase == "execution":
            return 5
        # Research prompts carry position snapshots as context, but do not
        # expose an executable order. Treating those fields as execution risk
        # would collapse every research call to P5.
        if phase == "analysis":
            return 2
        if any(token in text for token in ("quantity", "shares", "weight", "position", "holding")):
            return 4
        if any(token in text for token in ("price", "return", "risk", "drawdown", "order")):
            return 3
        return 2 if any(token in text for token in ("market", "news", "fundamental")) else 1

    @staticmethod
    def dependencies(role: str, phase: str) -> TaskDependencyState:
        if phase == "analysis" or role == "fundamental_filter":
            return TaskDependencyState(pending_conclusion=True)
        if phase == "risk" or role in {"decision_agent", "portfolio_strategist"}:
            return TaskDependencyState(pending_risk_judgement=True)
        if phase == "execution":
            return TaskDependencyState(pending_action=True)
        return TaskDependencyState()

    def role(self, payload: Mapping[str, Any]) -> str:
        explicit = payload.get("finscope_role")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        text = "\n".join(_walk_strings(payload.get("messages", [])))
        if "fundamental filter" in text.lower() or "fundamental_filter" in text:
            return "fundamental_filter"
        if "portfolio strategist" in text.lower() or "<DECISION>" in text:
            return "decision_agent"
        return "tool_agent"

    def _episode_mapper(self, episode: str) -> AliasMapper:
        with self.lock:
            if episode not in self.episode_mappers:
                self.episode_mappers[episode] = AliasMapper(
                    self.catalog, "EA", self.secret, episode
                )
            return self.episode_mappers[episode]

    def _finscope(self, episode: str, trading_day: str = "") -> Tuple[LocalPrivacyAgent, Any]:
        with self.lock:
            if episode not in self.agents:
                agent = (
                    self.privacy_bundle.agent
                    if self.privacy_bundle is not None
                    else LocalPrivacyAgent(
                        [entry.as_finscope() for entry in self.catalog.entries],
                        default_level=self.config.disclosure_level,
                    )
                )
                scope = agent.open_scope(
                    f"{self.config.benchmark}:{episode}",
                    trading_day or (episode if DATE_PATTERN.fullmatch(episode) else "2026-08-22"),
                    conversation_id=episode,
                )
                self.agents[episode] = agent
                self.scopes[episode] = scope
                controller = AdaptiveReplacementController(
                    self.risk_estimator,
                    threshold=self.config.adaptive_threshold,
                    default_level=self.config.disclosure_level,
                )
                controller.bind_scope(scope.id)
                self.adaptive_controllers[episode] = controller
                self.adaptive_runtimes[episode] = AdaptiveRuntime(agent, controller)
            return self.agents[episode], self.scopes[episode]

    def transform(self, payload: Dict[str, Any], episode: str) -> Tuple[Dict[str, Any], Any]:
        outbound = dict(payload)
        # These fields scope the local privacy controller and are not part of
        # the OpenAI request schema accepted by the upstream model service.
        outbound.pop("finscope_episode", None)
        outbound.pop("finscope_role", None)
        outbound.pop("finscope_task", None)
        outbound["model"] = self.config.upstream_model
        messages = outbound.get("messages", [])
        method = self.config.method
        if method in {"vanilla", "llm_rewrite"}:
            return outbound, None
        if method == "deletion":
            replacements = {
                entry.canonical_id: f"[REDACTED_{entry.entity_type.upper().replace(' ', '_')}]"
                for entry in self.catalog.entries
            }
            outbound["messages"] = self.catalog.replace(messages, replacements)
            return outbound, None
        if method == "global_alias":
            outbound["messages"] = self.global_mapper.sanitize(messages)
            return outbound, self.global_mapper
        if method == "episode_alias":
            mapper = self._episode_mapper(episode)
            outbound["messages"] = mapper.sanitize(messages)
            return outbound, mapper
        if method == "finscope":
            trading_day = self.trading_day(payload, episode)
            agent, scope = self._finscope(episode, trading_day)
            controller = self.adaptive_controllers[episode]
            runtime = self.adaptive_runtimes[episode]
            previous_context = self.adaptive_context.get(episode, {})
            day_boundary = bool(
                previous_context.get("trading_day")
                and previous_context.get("trading_day") != trading_day
            )
            pre_rotation = None
            if day_boundary:
                boundary_risk = controller.estimator.predict(controller.exposure)
                if boundary_risk.combined >= controller.threshold:
                    new_scope, reset = runtime.rotate_at_checkpoint(
                        scope,
                        {
                            "task_phase": previous_context.get("phase", ""),
                            "previous_trading_day": previous_context.get("trading_day", ""),
                            "next_trading_day": trading_day,
                        },
                        trading_day=trading_day,
                    )
                    scope = new_scope
                    self.scopes[episode] = new_scope
                    self.first_days[episode] = date.fromisoformat(trading_day)
                    pre_rotation = {
                        "old_scope_id": reset.old_scope_id,
                        "new_scope_id": reset.new_scope_id,
                        "reason": "risk_above_T_at_day_boundary",
                        "timing": "before_external_request",
                    }
                    # The boundary has been consumed before this request. Do
                    # not rotate again between the two roles of the new day.
                    day_boundary = False
            role = self.role(payload)
            phase = self.task_phase(role, payload)
            field_risk = self.field_risk(phase, payload)
            purpose = "execution" if phase == "execution" else ("risk" if phase == "risk" else "research")
            controller.bind_scope(scope.id)
            level = controller.choose_level(
                purpose=purpose,
                task_phase=phase,
                field_risk=field_risk,
            )
            outbound["messages"] = agent.sanitize(
                messages,
                scope,
                disclosure_level=level,
                purpose=purpose,
            )
            day = date.fromisoformat(trading_day)
            first_day = self.first_days.setdefault(episode, day)
            aliases = tuple(
                alias.upper()
                for alias in re.findall(r"FS_(?:ASSET|ORG|PORTFOLIO|STRATEGY|ACCOUNT|REF|ACTION|REL|INTENT)_[A-Z0-9]+", json.dumps(outbound.get("messages", "")))
            )
            bindings = agent.get_bindings(scope)
            by_alias = {item.alias: item for item in bindings}
            self.adaptive_context[episode] = {
                "trading_day": trading_day,
                "elapsed_days": max(0, (day - first_day).days),
                "role": role,
                "phase": phase,
                "purpose": purpose,
                "field_risk": field_risk,
                "level": level.name,
                "alias_occurrences": len(aliases),
                "assets": [by_alias[item].canonical_id for item in aliases if item in by_alias],
                "scope_id": scope.id,
                # A trading-day boundary is a local safe checkpoint. The
                # current request finishes under the old scope; rotation is
                # applied after its response, before the next request.
                "day_boundary": day_boundary,
                "pre_rotation": pre_rotation,
            }
            return outbound, (agent, scope)
        raise AssertionError("unreachable")

    def observe_adaptive(
        self,
        episode: str,
        *,
        output: Mapping[str, Any],
        restoration_status: str,
    ) -> Dict[str, Any]:
        """Update local exposure after a call and rotate only at a safe point."""

        if self.config.method != "finscope":
            return {}
        with self.lock:
            context = dict(self.adaptive_context.get(episode, {}))
            controller = self.adaptive_controllers.get(episode)
            runtime = self.adaptive_runtimes.get(episode)
            scope = self.scopes.get(episode)
            if controller is None or runtime is None or scope is None:
                return {}
            phase = str(context.get("phase", "analysis"))
            decision = controller.observe_call(
                alias_occurrences=int(context.get("alias_occurrences", 0)),
                elapsed_days=int(context.get("elapsed_days", 0)),
                visible_roles=(str(context.get("role", "")),),
                market_events=1,
                trade_events=1 if phase == "execution" else 0,
                assets=context.get("assets", ()),
                high_risk_events=1 if int(context.get("field_risk", 1)) >= 4 else 0,
                dependencies=self.dependencies(str(context.get("role", "")), phase),
                safe_checkpoint=phase in {"tool", "execution"}
                or bool(context.get("day_boundary")),
                task_phase=phase,
                field_risk=int(context.get("field_risk", 1)),
                purpose=str(context.get("purpose", "research")),
            )
            rotation = context.get("pre_rotation")
            if decision.decision.value != "keep":
                minimal_state = {
                    "task_phase": phase,
                    "trading_day": context.get("trading_day", ""),
                    "restoration_status": restoration_status,
                    "last_output_fingerprint": hashlib.sha256(
                        json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
                old_scope = scope
                new_scope, reset = runtime.rotate_at_checkpoint(
                    old_scope,
                    minimal_state,
                    trading_day=str(context.get("trading_day", "")) or None,
                )
                self.scopes[episode] = new_scope
                trading_day = str(context.get("trading_day", ""))
                if trading_day:
                    self.first_days[episode] = date.fromisoformat(trading_day)
                rotation = {
                    "old_scope_id": reset.old_scope_id,
                    "new_scope_id": reset.new_scope_id,
                    "reason": decision.reason,
                    "timing": "after_external_response",
                }
            return {
                "level": decision.level.name,
                "requested_level": str(context.get("level", decision.level.name)),
                "risk": {
                    "reid_at_1": decision.risk.reid_at_1,
                    "link_auc": decision.risk.link_auc,
                    "combined": decision.risk.combined,
                },
                "threshold_T": controller.threshold,
                "decision": decision.decision.value,
                "reason": decision.reason,
                "exposure_state": controller.exposure.as_dict(),
                "rotation": rotation,
                "rotation_count": controller.rotation_count,
                "estimator_fitted": controller.estimator.fitted,
            }

    def restore(
        self, response: Dict[str, Any], state: Any
    ) -> Tuple[Dict[str, Any], str, bool, List[Dict[str, Any]]]:
        method = self.config.method
        if method in {"vanilla", "deletion", "llm_rewrite"}:
            return response, "not_applicable", True, []
        if method in {"global_alias", "episode_alias"}:
            unknown = [
                alias
                for alias in ALIAS_PATTERN.findall(json.dumps(response, ensure_ascii=False))
                if alias.upper() not in state.reverse
            ]
            issues = [
                {
                    "code": "unknown_handle",
                    "severity": "error",
                    "message": "unknown or stale privacy handle",
                    "aliases": [alias],
                }
                for alias in unknown
            ]
            return (
                state.restore(response),
                "safe" if not unknown else "rejected",
                not unknown,
                issues,
            )
        agent, scope = state
        result = agent.restore_and_audit(response, scope)
        if result.status in {"safe", "needs_retry"} and isinstance(result.value, Mapping):
            return (
                dict(result.value),
                result.status,
                True,
                [asdict(item) for item in result.issues],
            )
        blocked = dict(response)
        choices = blocked.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            choices = [dict(item) for item in choices]
            choices[0]["message"] = {
                "role": "assistant",
                "content": json.dumps(
                    {"tool": "escalate_to_human", "args": {"reason": "privacy_restoration_rejected"}}
                ),
            }
            blocked["choices"] = choices
        return blocked, result.status, False, [asdict(item) for item in result.issues]

    def bindings(self, episode: str, state: Any) -> List[Dict[str, str]]:
        if self.config.method == "global_alias":
            return self.global_mapper.bindings()
        if self.config.method == "episode_alias":
            return state.bindings()
        if self.config.method == "finscope":
            agent, scope = state
            return [asdict(binding) for binding in agent.get_bindings(scope)]
        return []

    def rewrite_messages(self, payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        messages = payload.get("messages", [])
        replacements = {
            entry.canonical_id: entry.descriptor for entry in self.catalog.entries
        }
        generalized = self.catalog.replace(messages, replacements)
        if not isinstance(generalized, list):
            return [], {
                "status": "fallback",
                "usage": {},
                "latency_ms": 0.0,
                "outbound_sensitive": 0,
            }
        latest = None
        if isinstance(messages, list):
            for index in range(len(messages) - 1, -1, -1):
                message = messages[index]
                if isinstance(message, Mapping) and message.get("role") == "user":
                    latest = index
                    break
        if latest is None:
            return generalized, {
                "status": "no_user",
                "usage": {},
                "latency_ms": 0.0,
                "outbound_sensitive": 0,
            }
        original = messages[latest].get("content", "")
        prompt = (
            "Rewrite the following financial-agent message to remove or generalize all "
            "person, organization, account, case, product, asset, ticker and transaction "
            "identities. Preserve task facts, numbers, JSON structure and tool instructions. "
            "Do not infer or repeat an identity. Return only the rewritten message.\n\n"
            + (original if isinstance(original, str) else json.dumps(original, ensure_ascii=False))
        )
        rewrite_payload = {
            "model": self.config.upstream_model,
            "messages": [
                {"role": "system", "content": "You are a privacy-preserving financial text rewriter."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            # A rewrite is a preprocessing baseline, not an open-ended prose
            # generation.  Keeping its budget bounded prevents a verbose
            # rewriter from exhausting the task-model service's KV cache.
            "max_tokens": min(
                int(payload.get("max_tokens") or REWRITE_MAX_TOKENS),
                REWRITE_MAX_TOKENS,
            ),
            "stream": False,
        }
        started = time.perf_counter()
        try:
            response = self._post(rewrite_payload)
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty rewrite")
            generalized[latest] = dict(generalized[latest])
            generalized[latest]["content"] = self.catalog.replace(content.strip(), replacements)
            return generalized, {
                "status": "ok",
                "usage": response.get("usage", {}),
                "latency_ms": (time.perf_counter() - started) * 1000,
                "outbound_sensitive": self.catalog.count(original),
            }
        except Exception as exc:
            return generalized, {
                "status": "fallback",
                "error": str(exc)[:200],
                "usage": {},
                "latency_ms": (time.perf_counter() - started) * 1000,
                "outbound_sensitive": self.catalog.count(original),
            }

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        import httpx

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(
                self.config.upstream_url.rstrip("/") + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer local"},
            )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise TypeError("upstream response must be an object")
        return result

    def audit(self, record: Dict[str, Any]) -> None:
        with self.audit_lock:
            self.request_count += 1
            record["request_id"] = self.request_count
            with self.config.audit_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def create_app(config: ProxyConfig, entries: Sequence[CatalogEntry]):
    from fastapi import FastAPI, HTTPException

    controller = PrivacyController(config, entries)
    app = FastAPI(title="FinScope external benchmark privacy proxy")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "benchmark": config.benchmark,
            "method": config.method,
            "catalog_size": len(entries),
        }

    @app.get("/v1/models")
    def models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": config.upstream_model, "object": "model", "owned_by": "local"}],
        }

    @app.post("/v1/chat/completions")
    def completions(payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("stream"):
            raise HTTPException(status_code=400, detail="streaming is not supported")
        request_started = time.perf_counter()
        privacy_usage_before = (
            controller.privacy_bundle.usage()
            if controller.privacy_bundle is not None
            else {}
        )
        episode = controller.episode_id(payload)
        role = controller.role(payload)
        raw_messages = payload.get("messages", [])
        input_fingerprint = hashlib.sha256(
            json.dumps(
                raw_messages,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        input_sensitive = controller.catalog.count(raw_messages)
        rewrite = {"status": "not_applicable", "usage": {}, "latency_ms": 0.0}
        outbound, state = controller.transform(payload, episode)
        if config.method == "llm_rewrite":
            rewritten, rewrite = controller.rewrite_messages(payload)
            outbound["messages"] = rewritten
        outbound_sensitive = controller.catalog.count(outbound.get("messages", []))
        started = time.perf_counter()
        try:
            upstream = controller._post(outbound)
            task_latency_ms = (time.perf_counter() - started) * 1000
            upstream_sensitive = controller.catalog.count(upstream)
            restored, restoration_status, exact_restore, restoration_issues = controller.restore(
                upstream, state
            )
        except Exception as exc:
            controller.audit(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "benchmark": config.benchmark,
                    "method": config.method,
                    "episode_id": episode,
                    "role": role,
                    "status": "error",
                    "error": str(exc)[:500],
                    "input_fingerprint": input_fingerprint,
                    "input_sensitive": input_sensitive,
                    "outbound_sensitive": outbound_sensitive,
                    "rewrite": rewrite,
                }
            )
            raise HTTPException(status_code=502, detail="upstream model call failed") from exc
        total_latency_ms = (time.perf_counter() - request_started) * 1000
        decision_fingerprint = _decision_fingerprint(restored)
        privacy_model_usage = (
            usage_delta(privacy_usage_before, controller.privacy_bundle.usage())
            if controller.privacy_bundle is not None
            else {}
        )
        privacy_agent_metrics = {}
        adaptive_metrics = {}
        bindings_snapshot: List[Dict[str, str]] = []
        # Keep the observable alias bindings for every alias baseline.  The
        # public-prior attack is allowed to see handles and their repeated
        # use, but never the local mapping; omitting these snapshots makes
        # Global/Episode Alias look like a no-binding random baseline.
        if state is not None and config.method in {"global_alias", "episode_alias", "finscope"}:
            bindings_snapshot = controller.bindings(episode, state)
        if config.method == "finscope" and state is not None:
            agent, scope = state
            privacy_agent_metrics = agent.get_metrics(scope)
            adaptive_metrics = controller.observe_adaptive(
                episode,
                output=restored,
                restoration_status=restoration_status,
            )
        controller.audit(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "benchmark": config.benchmark,
                "method": config.method,
                "episode_id": episode,
                "trading_day": controller.trading_day(payload, episode),
                "role": role,
                "status": "ok",
                "input_fingerprint": input_fingerprint,
                "decision_fingerprint": decision_fingerprint,
                "input_sensitive": input_sensitive,
                "outbound_sensitive": outbound_sensitive,
                "upstream_sensitive": upstream_sensitive,
                "task_usage": upstream.get("usage", {}),
                "rewrite": rewrite,
                "task_latency_ms": task_latency_ms,
                "total_latency_ms": total_latency_ms,
                "privacy_model_usage": privacy_model_usage,
                "privacy_agent_metrics": privacy_agent_metrics,
                "adaptive": adaptive_metrics,
                "restoration_status": restoration_status,
                "restoration_issues": restoration_issues,
                "exact_restore": exact_restore if state is not None else None,
                "unsafe_repair": False,
                "bindings": bindings_snapshot,
                "attacker_view": {
                    "messages": outbound.get("messages", []),
                    "response": _external_response_view(upstream),
                },
            }
        )
        return restored

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("stockbench", "finvault"), required=True)
    parser.add_argument("--benchmark-root", default="")
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--upstream-url", required=True)
    parser.add_argument("--upstream-model", default="Qwen3.8-27B")
    parser.add_argument("--privacy-model-base-url", default="")
    parser.add_argument("--privacy-model-name", default="Qwen2.5-3B-Instruct")
    parser.add_argument(
        "--adaptive-threshold",
        type=float,
        default=float(os.environ.get("FINSCOPE_ADAPTIVE_T", "0.60")),
        help="risk threshold T used by FinScope Adaptive",
    )
    parser.add_argument(
        "--adaptive-calibration",
        default=os.environ.get("FINSCOPE_ADAPTIVE_CALIBRATION", ""),
        help="JSON prior-attack artifact used to fit the online risk estimator",
    )
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--disclosure-level", choices=("P1", "P2", "P3", "P4", "P5"), default="P1")
    parser.add_argument("--seed", default="finscope-external-benchmark-v1")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    import uvicorn

    args = parse_args()
    if args.benchmark == "stockbench":
        entries = stockbench_catalog()
    else:
        if not args.benchmark_root:
            raise SystemExit("--benchmark-root is required for FinVault")
        entries = finvault_catalog(Path(args.benchmark_root))
    config = ProxyConfig(
        benchmark=args.benchmark,
        method=args.method,
        upstream_url=args.upstream_url,
        upstream_model=args.upstream_model,
        audit_log=args.audit_log,
        disclosure_level=args.disclosure_level,
        seed=args.seed,
        timeout=args.timeout,
        privacy_model_base_url=args.privacy_model_base_url,
        privacy_model_name=args.privacy_model_name,
        adaptive_threshold=args.adaptive_threshold,
        adaptive_calibration=args.adaptive_calibration,
    )
    uvicorn.run(create_app(config, entries), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
