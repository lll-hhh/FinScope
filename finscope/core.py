"""Core implementation of the FinScope privacy mediation layer.

The implementation is intentionally small and deterministic at the API level:
all state is local to a :class:`FinScopeMediator`, aliases are stable only for a
single ``(task_id, trading_day)`` scope, and no mapping is persisted by default.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import math
import re
import secrets
import threading
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from .policy import (
    AdaptivePrivacyPolicy,
    PrivacyLevel,
    ResidualScanDecision,
    ResidualScanPolicy,
)
from .recognizer import EntityRecognizer, EntitySpan


JsonValue = Any


class FinScopeError(RuntimeError):
    """Base exception for mediator errors."""


class ScopeNotFoundError(FinScopeError):
    """Raised when a scope was closed or never existed."""


class ActionValidationError(FinScopeError):
    """Raised when a restored trading action is not safe to execute."""


@dataclass(frozen=True)
class Scope:
    """Public handle shared by the research, risk and trading agents."""

    id: str
    task_id: str
    trading_day: str
    conversation_id: str
    privacy_level: str
    created_at: datetime


@dataclass(frozen=True)
class ValidationResult:
    """Result of local action validation.

    ``action`` contains real asset identifiers and is safe to pass to a local
    execution engine only after this result has been accepted by the caller.
    """

    action: Dict[str, Any]
    valid: bool = True
    warnings: Tuple[str, ...] = ()


@dataclass
class _ScopeState:
    scope: Scope
    base_privacy_level: PrivacyLevel = PrivacyLevel.STANDARD
    effective_privacy_level: PrivacyLevel = PrivacyLevel.STANDARD
    real_to_alias: Dict[str, str] = field(default_factory=dict)
    alias_to_real: Dict[str, str] = field(default_factory=dict)
    alias_types: Dict[str, str] = field(default_factory=dict)
    alias_canonical: Dict[str, str] = field(default_factory=dict)
    alias_risks: Dict[str, int] = field(default_factory=dict)
    display_names: Dict[str, str] = field(default_factory=dict)
    surface_aliases: Dict[str, set] = field(default_factory=dict)
    escalation_reasons: List[str] = field(default_factory=list)
    safe_residual_fingerprints: List[str] = field(default_factory=list)
    consecutive_empty_scans: int = 0
    skipped_since_probe: int = 0
    last_scan_privacy_level: PrivacyLevel = PrivacyLevel.STANDARD
    metrics: Dict[str, int] = field(
        default_factory=lambda: {
            "assets_registered": 0,
            "entities_registered": 0,
            "aliases_issued": 0,
            "payloads_sanitized": 0,
            "payloads_restored": 0,
            "unknown_aliases": 0,
            "actions_validated": 0,
            "actions_rejected": 0,
            "recognizer_calls": 0,
            "recognizer_errors": 0,
            "entities_detected": 0,
            "privacy_escalations": 0,
            "effective_privacy_level": int(PrivacyLevel.STANDARD),
            "recognizer_skips": 0,
            "recognizer_probes": 0,
            "recognizer_new_replacements": 0,
            "recognizer_empty_scans": 0,
        }
    )


class FinScopeMediator:
    """Local privacy middleware for tool-using financial agents.

    A scope is reused by all agents participating in one task on one trading
    day.  Opening the same task on a different day automatically closes the old
    scope and generates fresh aliases, preventing cross-day linkage.

    ``asset_catalog`` is a local security master.  Each entry can be either a
    canonical string (``"Apple Inc."``) or a mapping with ``name`` and optional
    ``aliases`` (``{"name": "Apple Inc.", "aliases": ["AAPL"]}``).
    """

    ASSET_FIELD_NAMES = frozenset(
        {
            "asset",
            "asset_name",
            "symbol",
            "ticker",
            "security",
            "security_name",
            "instrument",
            "instrument_name",
            "underlying",
            "stock",
            "stock_name",
            "fund",
            "fund_name",
            "etf",
            "isin",
            "cusip",
        }
    )
    ASSET_COLLECTION_NAMES = frozenset(
        {
            "assets",
            "asset_pool",
            "candidate_pool",
            "candidates",
            "watchlist",
            "holdings",
            "holding",
            "positions",
            "position",
            "portfolio",
            "orders",
            "order",
            "trades",
            "trade",
            "transactions",
        }
    )
    ACTION_SIDES = frozenset({"buy", "sell", "hold", "short", "cover"})
    ENTITY_TYPE_ALIASES = {
        "asset": "ASSET",
        "institution": "ORG",
        "organization": "ORG",
        "portfolio": "PORTFOLIO",
        "strategy": "STRATEGY",
        "account": "ACCOUNT",
        "reference": "REF",
        "action": "ACTION",
        "relation": "REL",
        "intent": "INTENT",
    }
    SENSITIVE_FIELD_TYPES = {
        "institution": "institution",
        "institution_name": "institution",
        "account_id": "account",
        "portfolio_id": "portfolio",
        "strategy_id": "strategy",
        "strategy_name": "strategy",
    }
    _ALIAS_PATTERN = re.compile(
        r"(?<![A-Za-z0-9_])FS_(?:ASSET|ORG|PORTFOLIO|STRATEGY|ACCOUNT|REF|ACTION|REL|INTENT)_"
        r"[A-Z2-9]{8}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )

    def __init__(
        self,
        asset_catalog: Optional[Sequence[Union[str, Mapping[str, Any]]]] = None,
        *,
        strict_actions: bool = True,
        entity_recognizer: Optional[EntityRecognizer] = None,
        privacy_policy: Optional[AdaptivePrivacyPolicy] = None,
        residual_scan_policy: Optional[ResidualScanPolicy] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._scopes: Dict[str, _ScopeState] = {}
        self._task_index: Dict[Tuple[str, str], str] = {}
        self._catalog: List[Tuple[str, Tuple[str, ...]]] = []
        self.strict_actions = strict_actions
        self.entity_recognizer = entity_recognizer
        self.privacy_policy = privacy_policy or AdaptivePrivacyPolicy()
        self.residual_scan_policy = residual_scan_policy or ResidualScanPolicy()
        self._catalog_lookup: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        self._catalog_entities: List[str] = []
        catalog_owners: Dict[str, str] = {}
        for entry in asset_catalog or ():
            if isinstance(entry, str):
                name = entry
                aliases = ()
            elif isinstance(entry, Mapping):
                name = entry.get("name") or entry.get("symbol") or entry.get("ticker")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("asset catalog entries require a non-empty name")
                aliases = entry.get("aliases", ())
                if isinstance(aliases, str):
                    aliases = (aliases,)
            else:
                raise TypeError("asset catalog entries must be strings or mappings")
            name = self._require_text(name, "asset name")
            normalized_aliases = tuple(
                str(alias).strip() for alias in aliases if str(alias).strip()
            )
            owner = self._normalize_entity(name)
            for identifier in (name,) + normalized_aliases:
                identifier_key = self._normalize_entity(identifier)
                previous_owner = catalog_owners.get(identifier_key)
                if previous_owner is not None and previous_owner != owner:
                    raise ValueError(
                        f"asset identifier {identifier!r} belongs to multiple catalog entries"
                    )
                catalog_owners[identifier_key] = owner
            self._catalog.append((name, normalized_aliases))
            self._catalog_entities.extend((name,) + normalized_aliases)
            for identifier in (name,) + normalized_aliases:
                self._catalog_lookup[self._normalize_entity(identifier)] = (
                    name,
                    normalized_aliases,
                )

    @classmethod
    def from_local_model(
        cls,
        model_path: str,
        asset_catalog: Optional[Sequence[Union[str, Mapping[str, Any]]]] = None,
        *,
        device: str = "cpu",
        max_new_tokens: int = 256,
        strict_actions: bool = True,
        privacy_policy: Optional[AdaptivePrivacyPolicy] = None,
        residual_scan_policy: Optional[ResidualScanPolicy] = None,
    ) -> "FinScopeMediator":
        """Create a mediator whose sensitive-entity decisions use a local LM."""

        from .recognizer import CatalogEntityRecognizer, TransformersEntityRecognizer

        catalog_entities: List[str] = []
        for entry in asset_catalog or ():
            if isinstance(entry, str):
                catalog_entities.append(entry)
            elif isinstance(entry, Mapping):
                name = entry.get("name") or entry.get("symbol") or entry.get("ticker")
                if isinstance(name, str):
                    catalog_entities.append(name)
                aliases = entry.get("aliases", ())
                if isinstance(aliases, str):
                    aliases = (aliases,)
                catalog_entities.extend(
                    alias for alias in aliases if isinstance(alias, str)
                )
        fallback = CatalogEntityRecognizer(catalog_entities) if catalog_entities else None
        recognizer = TransformersEntityRecognizer(
            model_path,
            device=device,
            max_new_tokens=max_new_tokens,
            fallback=fallback,
        )
        return cls(
            asset_catalog,
            strict_actions=strict_actions,
            entity_recognizer=recognizer,
            privacy_policy=privacy_policy,
            residual_scan_policy=residual_scan_policy,
        )

    # ------------------------------------------------------------------
    # Scope lifecycle
    # ------------------------------------------------------------------
    def open_scope(
        self,
        task_id: str,
        trading_day: Union[str, date],
        *,
        conversation_id: Optional[str] = None,
        privacy_level: Union[PrivacyLevel, str, int] = PrivacyLevel.STANDARD,
    ) -> Scope:
        """Open a stable task/day/conversation scope and preload the local list."""

        task_id = self._require_text(task_id, "task_id")
        day = self._normalize_day(trading_day)
        conversation_id = self._require_text(
            conversation_id or task_id,
            "conversation_id",
        )
        base_level = PrivacyLevel.parse(privacy_level)
        scope_key = (task_id, conversation_id)
        with self._lock:
            previous_id = self._task_index.get(scope_key)
            if previous_id is not None:
                previous = self._scopes.get(previous_id)
                if previous is not None and previous.scope.trading_day == day:
                    if base_level > previous.effective_privacy_level:
                        previous.effective_privacy_level = base_level
                        previous.base_privacy_level = max(
                            previous.base_privacy_level,
                            base_level,
                        )
                        previous.metrics["effective_privacy_level"] = int(base_level)
                    return previous.scope
                if previous is not None:
                    self._close_state(previous_id, previous)

            scope = Scope(
                id=f"scope-{secrets.token_urlsafe(9)}",
                task_id=task_id,
                trading_day=day,
                conversation_id=conversation_id,
                privacy_level=base_level.name.lower(),
                created_at=datetime.now(timezone.utc),
            )
            state = _ScopeState(
                scope=scope,
                base_privacy_level=base_level,
                effective_privacy_level=base_level,
            )
            state.metrics["effective_privacy_level"] = int(base_level)
            self._scopes[scope.id] = state
            self._task_index[scope_key] = scope.id
            for canonical, aliases in self._catalog:
                self._register_asset(state, canonical, aliases)
            return scope

    def rotate_day(self, trading_day: Union[str, date]) -> List[str]:
        """Close every active scope from a different trading day."""

        day = self._normalize_day(trading_day)
        closed: List[str] = []
        with self._lock:
            for scope_id, state in list(self._scopes.items()):
                if state.scope.trading_day != day:
                    self._close_state(scope_id, state)
                    closed.append(scope_id)
        return closed

    @contextmanager
    def task_scope(
        self,
        task_id: str,
        trading_day: Union[str, date],
        *,
        conversation_id: Optional[str] = None,
        privacy_level: Union[PrivacyLevel, str, int] = PrivacyLevel.STANDARD,
    ) -> Iterator[Scope]:
        """Context manager that erases a mapping when the task finishes."""

        scope = self.open_scope(
            task_id,
            trading_day,
            conversation_id=conversation_id,
            privacy_level=privacy_level,
        )
        try:
            yield scope
        finally:
            with self._lock:
                state = self._scopes.get(scope.id)
                if state is not None:
                    self._close_state(scope.id, state)

    def close_scope(self, scope: Union[Scope, str]) -> None:
        """Erase all real-to-alias bindings for a scope."""

        scope_id = scope.id if isinstance(scope, Scope) else scope
        with self._lock:
            state = self._scopes.get(scope_id)
            if state is None:
                raise ScopeNotFoundError(f"scope {scope_id!r} is not active")
            self._close_state(scope_id, state)

    def _close_state(self, scope_id: str, state: _ScopeState) -> None:
        self._scopes.pop(scope_id, None)
        scope_key = (state.scope.task_id, state.scope.conversation_id)
        if self._task_index.get(scope_key) == scope_id:
            self._task_index.pop(scope_key, None)
        state.real_to_alias.clear()
        state.alias_to_real.clear()
        state.alias_types.clear()
        state.alias_canonical.clear()
        state.alias_risks.clear()
        state.display_names.clear()
        state.surface_aliases.clear()
        state.escalation_reasons.clear()
        state.safe_residual_fingerprints.clear()

    def _state(self, scope: Union[Scope, str]) -> _ScopeState:
        scope_id = scope.id if isinstance(scope, Scope) else scope
        with self._lock:
            state = self._scopes.get(scope_id)
            if state is None:
                raise ScopeNotFoundError(f"scope {scope_id!r} is not active")
            return state

    # ------------------------------------------------------------------
    # Local entity registration and mapping
    # ------------------------------------------------------------------
    def register_asset(
        self,
        scope: Union[Scope, str],
        canonical: str,
        aliases: Sequence[str] = (),
    ) -> str:
        """Register an asset and return its current scoped alias."""

        state = self._state(scope)
        with self._lock:
            return self._register_asset(state, canonical, aliases)

    def _register_asset(
        self,
        state: _ScopeState,
        canonical: str,
        aliases: Sequence[str] = (),
    ) -> str:
        return self._register_entity(state, canonical, aliases, "asset")

    def _register_entity(
        self,
        state: _ScopeState,
        canonical: str,
        aliases: Sequence[str],
        entity_type: str,
        *,
        risk: int = 2,
        reuse_alias: Optional[str] = None,
        restore_value: Optional[str] = None,
    ) -> str:
        canonical = self._require_text(canonical, "canonical")
        entity_type = entity_type.casefold()
        if entity_type == "organization":
            entity_type = "institution"
        if entity_type not in self.ENTITY_TYPE_ALIASES:
            raise ValueError(f"unsupported entity type {entity_type!r}")
        canonical_key = self._mapping_key(entity_type, canonical)
        existing = state.real_to_alias.get(canonical_key)
        if existing is None:
            existing = reuse_alias
            if existing is None:
                existing = self._new_alias(state.alias_to_real, entity_type)
                state.alias_to_real[existing] = restore_value or canonical
                state.alias_canonical[existing] = canonical
                state.alias_types[existing] = entity_type
                state.metrics["aliases_issued"] += 1
            elif existing not in state.alias_to_real:
                raise ValueError(f"cannot reuse unknown alias {existing!r}")
        state.real_to_alias[canonical_key] = existing
        state.display_names[canonical_key] = canonical
        self._bind_surface(state, canonical, existing)
        for alternate in aliases:
            if isinstance(alternate, str) and alternate.strip():
                alternate_key = self._mapping_key(entity_type, alternate)
                state.real_to_alias[alternate_key] = existing
                state.display_names[alternate_key] = alternate
                self._bind_surface(state, alternate, existing)
        state.alias_risks[existing] = max(state.alias_risks.get(existing, 1), risk)
        state.metrics["assets_registered"] = sum(
            item_type == "asset" for item_type in state.alias_types.values()
        )
        state.metrics["entities_registered"] = len(state.alias_types)
        return existing

    def _bind_surface(self, state: _ScopeState, surface: str, alias: str) -> None:
        surface_key = self._normalize_entity(surface)
        state.surface_aliases.setdefault(surface_key, set()).add(alias)

    def _find_reference_alias(self, state: _ScopeState, target: Optional[str]) -> Optional[str]:
        if not isinstance(target, str) or not target.strip():
            return None
        alias_match = self._ALIAS_PATTERN.fullmatch(target.strip())
        if alias_match is not None:
            alias = alias_match.group(0).upper()
            return alias if alias in state.alias_to_real else None
        aliases = state.surface_aliases.get(self._normalize_entity(target), set())
        return next(iter(aliases)) if len(aliases) == 1 else None

    @classmethod
    def _new_alias(cls, existing: Mapping[str, str], entity_type: str) -> str:
        prefix = cls.ENTITY_TYPE_ALIASES[entity_type]
        while True:
            token = secrets.token_hex(5).upper().replace("0", "A").replace("1", "B")
            # Base16 contains 0/1, which are replaced above so the token is
            # visually distinct from real tickers and remains easy to parse.
            alias = f"FS_{prefix}_{token[:8]}"
            if alias not in existing:
                return alias

    def _register_structured_from_payload(
        self,
        value: JsonValue,
        state: _ScopeState,
        privacy_level: PrivacyLevel,
        key_hint: str = "",
    ) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_name = str(key).casefold()
                if key_name in self.ASSET_FIELD_NAMES and self.privacy_policy.protects(
                    "asset", privacy_level
                ):
                    self._register_entity_values(item, state, "asset")
                elif (
                    key_name in self.SENSITIVE_FIELD_TYPES
                    and self.privacy_policy.protects(
                        self.SENSITIVE_FIELD_TYPES[key_name], privacy_level
                    )
                ):
                    self._register_entity_values(
                        item,
                        state,
                        self.SENSITIVE_FIELD_TYPES[key_name],
                    )
                elif key_name in self.ASSET_COLLECTION_NAMES and self.privacy_policy.protects(
                    "asset", privacy_level
                ):
                    self._register_asset_collection(item, state)
                self._register_structured_from_payload(
                    item,
                    state,
                    privacy_level,
                    key_name,
                )
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                self._register_structured_from_payload(
                    item,
                    state,
                    privacy_level,
                    key_hint,
                )

    def _model_sanitize_string(
        self,
        text: str,
        state: _ScopeState,
        privacy_level: PrivacyLevel,
        *,
        force_model_scan: bool = False,
    ) -> str:
        if self.entity_recognizer is None or not text.strip():
            return text
        scan_decision = self.residual_scan_policy.decide(
            text,
            model_calls=state.metrics["recognizer_calls"],
            consecutive_empty_scans=state.consecutive_empty_scans,
            skipped_since_probe=state.skipped_since_probe,
            safe_fingerprints=state.safe_residual_fingerprints,
            privacy_level=privacy_level,
            last_scan_level=state.last_scan_privacy_level,
            force=force_model_scan,
        )
        if not scan_decision.should_scan:
            state.metrics["recognizer_skips"] += 1
            state.skipped_since_probe += 1
            return text
        if scan_decision.reason == "periodic-probe":
            state.metrics["recognizer_probes"] += 1
        if scan_decision.reason in {
            "periodic-probe",
            "forced",
            "privacy-escalation",
        }:
            self.entity_recognizer.clear_cache()
        state.metrics["recognizer_calls"] += 1
        state.skipped_since_probe = 0
        state.last_scan_privacy_level = privacy_level
        try:
            # The security-master pass already ran, so the model sees only
            # residual text and existing aliases, never the raw known list.
            entities = self.entity_recognizer.recognize(text, ())
        except Exception:
            state.metrics["recognizer_errors"] += 1
            state.consecutive_empty_scans = 0
            return text
        accepted_entities: List[EntitySpan] = []
        for entity in entities:
            if not isinstance(entity, EntitySpan):
                continue
            entity_type = entity.entity_type.casefold()
            if entity_type == "organization":
                entity_type = "institution"
            if entity_type not in self.ENTITY_TYPE_ALIASES:
                continue
            if entity.text != entity.text.strip() or len(entity.text) > 128:
                continue
            if self._ALIAS_PATTERN.fullmatch(entity.text):
                continue
            if not self.privacy_policy.protects(
                entity_type,
                privacy_level,
                entity.risk,
            ):
                continue
            text_key = self._normalize_entity(entity.text)
            known_asset_entry = self._catalog_lookup.get(text_key)
            if known_asset_entry is not None and entity_type != "asset":
                # The local security master is authoritative when a small
                # model mistakes a listed company or fund for an institution.
                entity_type = "asset"
                entity = EntitySpan(
                    start=entity.start,
                    end=entity.end,
                    text=entity.text,
                    entity_type="asset",
                    canonical=entity.canonical,
                    confidence=entity.confidence,
                    refers_to=entity.refers_to,
                    risk=entity.risk,
                )
            catalog_entry = known_asset_entry if entity_type == "asset" else None
            if catalog_entry is None and entity.canonical and entity_type == "asset":
                canonical_key = self._normalize_entity(entity.canonical)
                candidate_entry = self._catalog_lookup.get(canonical_key)
                if candidate_entry is not None:
                    known_names = {
                        self._normalize_entity(candidate_entry[0]),
                        *(self._normalize_entity(alias) for alias in candidate_entry[1]),
                    }
                    # A model may attach a known canonical ID, but the span
                    # itself must still be one of that asset's known forms.
                    if text_key not in known_names:
                        continue
            accepted_entities.append(entity)

        replacements: List[Tuple[int, int, str]] = []
        deferred_references: List[EntitySpan] = []
        for entity in accepted_entities:
            entity_type = entity.entity_type.casefold()
            if entity_type == "organization":
                entity_type = "institution"
            if entity_type == "reference":
                deferred_references.append(entity)
                continue
            catalog_entry = (
                self._catalog_lookup.get(self._normalize_entity(entity.text))
                if entity_type == "asset"
                else None
            )
            if catalog_entry is None and entity.canonical and entity_type == "asset":
                catalog_entry = self._catalog_lookup.get(
                    self._normalize_entity(entity.canonical)
                )
            if catalog_entry is None:
                canonical = entity.canonical or entity.text
                aliases: Tuple[str, ...] = ()
            else:
                canonical, aliases = catalog_entry
            alias = self._register_entity(
                state,
                canonical,
                aliases + (entity.text,),
                entity_type,
                risk=entity.risk,
                restore_value=(
                    entity.text
                    if entity_type in {"action", "relation", "intent"}
                    else None
                ),
            )
            replacements.append((entity.start, entity.end, alias))
            state.metrics["entities_detected"] += 1

        # Resolve pronouns after direct entities so a reference in the same
        # sentence can reuse the antecedent's alias instead of creating a new ID.
        for entity in deferred_references:
            reuse_alias = self._find_reference_alias(
                state,
                entity.refers_to or entity.canonical,
            )
            canonical = (
                state.alias_to_real[reuse_alias]
                if reuse_alias is not None
                else entity.canonical or entity.text
            )
            alias = self._register_entity(
                state,
                canonical,
                (entity.text,),
                "reference",
                risk=entity.risk,
                reuse_alias=reuse_alias,
            )
            replacements.append((entity.start, entity.end, alias))
            state.metrics["entities_detected"] += 1

        sanitized = text
        for start, end, alias in sorted(replacements, reverse=True):
            sanitized = sanitized[:start] + alias + sanitized[end:]
        if replacements:
            state.consecutive_empty_scans = 0
            state.metrics["recognizer_new_replacements"] += len(replacements)
        else:
            state.consecutive_empty_scans += 1
            state.metrics["recognizer_empty_scans"] += 1
            fingerprint = self.residual_scan_policy.fingerprint(text)
            if fingerprint not in state.safe_residual_fingerprints:
                state.safe_residual_fingerprints.append(fingerprint)
                if (
                    len(state.safe_residual_fingerprints)
                    > self.residual_scan_policy.max_safe_templates
                ):
                    state.safe_residual_fingerprints.pop(0)
        # If the model returned only one occurrence, finish replacing any
        # surface that has exactly one meaning in the current scope.
        return self._replace_assets(sanitized, state)

    def _sanitize_residual_value(
        self,
        value: JsonValue,
        state: _ScopeState,
        privacy_level: PrivacyLevel,
        key_hint: str = "",
        force_model_scan: bool = False,
    ) -> JsonValue:
        if isinstance(value, str):
            return self._model_sanitize_string(
                value,
                state,
                privacy_level,
                force_model_scan=force_model_scan,
            )
        if isinstance(value, Mapping):
            return {
                key: self._sanitize_residual_value(
                    item,
                    state,
                    privacy_level,
                    str(key).casefold(),
                    force_model_scan,
                )
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return [
                self._sanitize_residual_value(
                    item,
                    state,
                    privacy_level,
                    key_hint,
                    force_model_scan,
                )
                for item in value
            ]
        return value

    def _register_entity_values(
        self,
        value: JsonValue,
        state: _ScopeState,
        entity_type: str,
    ) -> None:
        if isinstance(value, str) and value.strip():
            if not self._ALIAS_PATTERN.search(value) and not self._looks_like_non_asset_text(value):
                self._register_entity(state, value, (), entity_type)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                self._register_entity_values(item, state, entity_type)
        elif isinstance(value, Mapping):
            for key in ("name", "symbol", "ticker", "asset", "security"):
                if isinstance(value.get(key), str):
                    self._register_entity(state, value[key], (), entity_type)

    def _register_asset_collection(self, value: JsonValue, state: _ScopeState) -> None:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                if isinstance(item, str):
                    self._register_entity_values(item, state, "asset")
                elif isinstance(item, Mapping):
                    for key in self.ASSET_FIELD_NAMES:
                        if key in item:
                            self._register_entity_values(item[key], state, "asset")
        elif isinstance(value, Mapping):
            found_asset_field = False
            for key, item in value.items():
                if str(key).casefold() in self.ASSET_FIELD_NAMES:
                    self._register_entity_values(item, state, "asset")
                    found_asset_field = True
            if not found_asset_field:
                # Portfolio/holding maps commonly use symbols as JSON keys:
                # {"AAPL": 0.25, "MSFT": 0.30}.
                asset_keyed = bool(value) and all(
                    isinstance(item, (int, float)) and not isinstance(item, bool)
                    for item in value.values()
                )
                if asset_keyed:
                    for key in value:
                        if isinstance(key, str):
                            self._register_entity_values(key, state, "asset")

    @staticmethod
    def _looks_like_non_asset_text(value: str) -> bool:
        """Avoid treating a prose sentence in an asset field as a security."""

        text = value.strip()
        return len(text) > 120 or "\n" in text

    # ------------------------------------------------------------------
    # Sanitization and restoration
    # ------------------------------------------------------------------
    def sanitize(
        self,
        payload: JsonValue,
        scope: Union[Scope, str],
        *,
        privacy_level: Optional[Union[PrivacyLevel, str, int]] = None,
        force_model_scan: bool = False,
    ) -> JsonValue:
        """Run deterministic first-pass and model-assisted residual sanitization."""

        state = self._state(scope)
        with self._lock:
            decision = self.privacy_policy.decide(
                payload,
                state.base_privacy_level,
                state.effective_privacy_level,
                state.metrics["payloads_sanitized"],
                privacy_level,
            )
            if decision.level > state.effective_privacy_level:
                state.metrics["privacy_escalations"] += 1
            state.effective_privacy_level = decision.level
            state.metrics["effective_privacy_level"] = int(decision.level)
            for reason in decision.reasons:
                if reason not in state.escalation_reasons:
                    state.escalation_reasons.append(reason)

            self._register_structured_from_payload(
                payload,
                state,
                decision.level,
            )
            first_pass = self._sanitize_value(payload, state)
            sanitized = self._sanitize_residual_value(
                first_pass,
                state,
                decision.level,
                force_model_scan=force_model_scan,
            )
            state.metrics["payloads_sanitized"] += 1
            return sanitized

    def sanitize_prompt(
        self,
        prompt: str,
        scope: Union[Scope, str],
        *,
        privacy_level: Optional[Union[PrivacyLevel, str, int]] = None,
        force_model_scan: bool = False,
    ) -> str:
        result = self.sanitize(
            prompt,
            scope,
            privacy_level=privacy_level,
            force_model_scan=force_model_scan,
        )
        if not isinstance(result, str):
            raise TypeError("sanitize_prompt expects a string")
        return result

    def sanitize_tool_result(
        self,
        result: JsonValue,
        scope: Union[Scope, str],
        *,
        privacy_level: Optional[Union[PrivacyLevel, str, int]] = None,
        force_model_scan: bool = False,
    ) -> JsonValue:
        return self.sanitize(
            result,
            scope,
            privacy_level=privacy_level,
            force_model_scan=force_model_scan,
        )

    def sanitize_messages(
        self,
        messages: Sequence[Mapping[str, Any]],
        scope: Union[Scope, str],
        *,
        privacy_level: Optional[Union[PrivacyLevel, str, int]] = None,
        force_model_scan: bool = False,
    ) -> List[Dict[str, Any]]:
        result = self.sanitize(
            list(messages),
            scope,
            privacy_level=privacy_level,
            force_model_scan=force_model_scan,
        )
        if not isinstance(result, list):
            raise TypeError("messages must sanitize to a list")
        return result

    def _sanitize_value(
        self,
        value: JsonValue,
        state: _ScopeState,
        key_hint: str = "",
    ) -> JsonValue:
        if isinstance(value, str):
            return self._replace_assets(value, state)
        if isinstance(value, Mapping):
            sanitized: Dict[Any, Any] = {}
            for key, item in value.items():
                output_key = key
                if isinstance(key, str) and key_hint in self.ASSET_COLLECTION_NAMES:
                    output_key = self._replace_assets(key, state)
                sanitized[output_key] = self._sanitize_value(item, state, str(key).casefold())
            return sanitized
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._sanitize_value(item, state, key_hint) for item in value]
        return value

    def _replace_assets(self, value: str, state: _ScopeState) -> str:
        if not state.real_to_alias:
            return value
        # Longer names first prevents a short ticker/name from consuming part
        # of a longer security name.  Boundaries avoid changing ordinary words.
        candidates = sorted(
            state.real_to_alias,
            key=lambda item: len(state.display_names.get(item, "")),
            reverse=True,
        )
        patterns: List[str] = []
        replacements: Dict[str, str] = {}
        for mapping_key in candidates:
            display = state.display_names.get(mapping_key)
            if not display:
                continue
            if len(state.surface_aliases.get(self._normalize_entity(display), ())) != 1:
                # Same surface form has multiple semantic meanings. Let the
                # residual model choose a concrete occurrence instead of a
                # dangerous global replacement.
                continue
            patterns.append(self._entity_pattern(display))
            replacements[display.casefold()] = state.real_to_alias[mapping_key]
        if not patterns:
            return value
        regex = re.compile(r"(?:" + "|".join(patterns) + r")", re.IGNORECASE)
        return regex.sub(
            lambda match: replacements.get(match.group(0).casefold(), match.group(0)),
            value,
        )

    @staticmethod
    def _entity_pattern(entity: str) -> str:
        """Build ASCII boundaries without blocking CJK-adjacent names."""

        escaped = re.escape(entity)
        left = (
            r"(?<![A-Za-z0-9_])"
            if entity and entity[0].isascii() and entity[0].isalnum()
            else ""
        )
        right = (
            r"(?![A-Za-z0-9_])"
            if entity and entity[-1].isascii() and entity[-1].isalnum()
            else ""
        )
        return left + escaped + right

    def restore_output(self, output: JsonValue, scope: Union[Scope, str]) -> JsonValue:
        """Restore aliases in an external model response locally."""

        state = self._state(scope)
        with self._lock:
            restored = self._restore_value(output, state)
            state.metrics["payloads_restored"] += 1
            return restored

    def _restore_value(self, value: JsonValue, state: _ScopeState) -> JsonValue:
        if isinstance(value, str):
            return self._replace_aliases(value, state)
        if isinstance(value, Mapping):
            return {
                self._replace_aliases(key, state) if isinstance(key, str) else key:
                self._restore_value(item, state)
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._restore_value(item, state) for item in value]
        return value

    def _replace_aliases(self, value: str, state: _ScopeState) -> str:
        if not state.alias_to_real:
            return value
        regex = self._ALIAS_PATTERN

        def replace(match: re.Match[str]) -> str:
            alias = match.group(0).upper()
            real = state.alias_to_real.get(alias)
            if real is None:
                state.metrics["unknown_aliases"] += 1
                return alias
            return real

        return regex.sub(replace, value)

    # ------------------------------------------------------------------
    # External-call and execution boundary helpers
    # ------------------------------------------------------------------
    def call_external(
        self,
        payload: JsonValue,
        llm_call: Callable[[JsonValue], JsonValue],
        scope: Union[Scope, str],
        *,
        privacy_level: Optional[Union[PrivacyLevel, str, int]] = None,
        force_model_scan: bool = False,
    ) -> JsonValue:
        """Run an external call with sanitized input and locally restored output."""

        sanitized = self.sanitize(
            payload,
            scope,
            privacy_level=privacy_level,
            force_model_scan=force_model_scan,
        )
        response = llm_call(sanitized)
        return self.restore_output(response, scope)

    def validate_action(
        self,
        action: Mapping[str, Any],
        scope: Union[Scope, str],
    ) -> ValidationResult:
        """Restore and validate a model-generated trading action locally.

        The validator intentionally accepts a small provider-neutral schema:
        ``asset``/``symbol``/``ticker``/``instrument``, ``side`` or ``action``,
        and optional numeric ``quantity``/``weight``.  Unknown aliases and
        unknown assets are rejected before an execution adapter sees the action.
        """

        if not isinstance(action, Mapping):
            raise ActionValidationError("trading action must be a mapping")
        state = self._state(scope)
        with self._lock:
            try:
                self._reject_unknown_aliases(action, state)
                restored = self._restore_action(dict(action), state)
                if not isinstance(restored, dict):  # pragma: no cover - defensive
                    raise ActionValidationError(
                        "action restoration produced a non-object"
                    )
                self._validate_action_fields(restored, state)
            except ActionValidationError:
                state.metrics["actions_rejected"] += 1
                raise
            state.metrics["actions_validated"] += 1
            return ValidationResult(action=restored)

    def _reject_unknown_aliases(self, value: JsonValue, state: _ScopeState) -> None:
        if isinstance(value, str):
            for alias in self._ALIAS_PATTERN.findall(value):
                if alias.upper() not in state.alias_to_real:
                    state.metrics["unknown_aliases"] += 1
                    raise ActionValidationError(f"unknown asset alias {alias!r}")
        elif isinstance(value, Mapping):
            for item in value.values():
                self._reject_unknown_aliases(item, state)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                self._reject_unknown_aliases(item, state)

    def _restore_action(
        self,
        action: Dict[str, Any],
        state: _ScopeState,
    ) -> Dict[str, Any]:
        restored: Dict[str, Any] = {}
        for key, value in action.items():
            key_name = str(key).casefold()
            matches = list(self._ALIAS_PATTERN.finditer(value)) if isinstance(value, str) else []
            if len(matches) != 1:
                restored[key] = self._restore_value(value, state)
                continue
            alias = matches[0].group(0).upper()
            prefix = alias.split("_", 2)[1]
            if key_name in self.ASSET_FIELD_NAMES and prefix != "ASSET":
                restored[key] = self._restore_value(value, state)
                continue
            if key_name in {"side", "action", "order_side"} and prefix != "ACTION":
                restored[key] = self._restore_value(value, state)
                continue
            # The general restore preserves wrappers such as "$ALIAS's".
            # For a typed action field, one known alias is unambiguous and its
            # real value is the only safe value to pass to an executor.
            restored[key] = state.alias_canonical.get(
                alias,
                state.alias_to_real[alias],
            )
        return restored

    def _validate_action_fields(
        self,
        action: MutableMapping[str, Any],
        state: _ScopeState,
    ) -> None:
        asset_key = next((key for key in self.ASSET_FIELD_NAMES if key in action), None)
        if asset_key is not None:
            asset = action[asset_key]
            if not isinstance(asset, str) or not asset.strip():
                raise ActionValidationError(f"{asset_key} must be a non-empty asset identifier")
            if self._mapping_key("asset", asset) not in state.real_to_alias:
                raise ActionValidationError(f"asset {asset!r} was not registered in this scope")

        side_key = next((key for key in ("side", "action", "order_side") if key in action), None)
        if side_key is not None:
            side = action[side_key]
            if not isinstance(side, str) or side.casefold() not in self.ACTION_SIDES:
                raise ActionValidationError(f"unsupported order side {side!r}")

        for key, value in action.items():
            key_name = str(key).casefold()
            if key_name in {"quantity", "qty", "shares", "notional", "price", "weight", "allocation"}:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ActionValidationError(f"{key} must be a finite number")
                if value < 0:
                    raise ActionValidationError(f"{key} cannot be negative")
                if key_name in {"weight", "allocation"} and value > 1:
                    raise ActionValidationError(f"{key} must be a decimal fraction in [0, 1]")

        if self.strict_actions and (asset_key is None or side_key is None):
            raise ActionValidationError("action must include both an asset and an order side")

    @staticmethod
    def _normalize_entity(value: str) -> str:
        return " ".join(value.strip().casefold().split())

    @classmethod
    def _mapping_key(cls, entity_type: str, value: str) -> str:
        if entity_type == "organization":
            entity_type = "institution"
        return f"{entity_type}:{cls._normalize_entity(value)}"

    @staticmethod
    def _normalize_day(value: Union[str, date]) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str) and value.strip():
            try:
                return date.fromisoformat(value.strip()).isoformat()
            except ValueError as exc:
                raise ValueError("trading_day must be an ISO date (YYYY-MM-DD)") from exc
        raise TypeError("trading_day must be a date or ISO date string")

    @staticmethod
    def _require_text(value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
        return value.strip()

    def get_metrics(self, scope: Union[Scope, str]) -> Dict[str, int]:
        """Return a copy of local counters for experiments and audit logs."""

        state = self._state(scope)
        with self._lock:
            return dict(state.metrics)

    def set_privacy_level(
        self,
        scope: Union[Scope, str],
        privacy_level: Union[PrivacyLevel, str, int],
    ) -> PrivacyLevel:
        """Raise the current level for a scope; lowering requires a new scope."""

        state = self._state(scope)
        requested = PrivacyLevel.parse(privacy_level)
        with self._lock:
            if requested > state.effective_privacy_level:
                state.effective_privacy_level = requested
                state.metrics["privacy_escalations"] += 1
                state.metrics["effective_privacy_level"] = int(requested)
            return state.effective_privacy_level

    def get_privacy_status(self, scope: Union[Scope, str]) -> Dict[str, Any]:
        """Return local-only adaptive policy state for evaluation and audits."""

        state = self._state(scope)
        with self._lock:
            return {
                "base_level": state.base_privacy_level.name.lower(),
                "effective_level": state.effective_privacy_level.name.lower(),
                "reasons": tuple(state.escalation_reasons),
                "conversation_id": state.scope.conversation_id,
                "trading_day": state.scope.trading_day,
                "scan_mode": self.residual_scan_policy.mode,
                "consecutive_empty_scans": state.consecutive_empty_scans,
                "skipped_since_probe": state.skipped_since_probe,
                "safe_template_count": len(state.safe_residual_fingerprints),
            }

    def get_mapping_records(self, scope: Union[Scope, str]) -> List[Dict[str, Any]]:
        """Return a trusted local mapping snapshot with semantic metadata."""

        state = self._state(scope)
        with self._lock:
            return [
                {
                    "alias": alias,
                    "restore_value": real,
                    "canonical": state.alias_canonical.get(alias, real),
                    "type": state.alias_types.get(alias, "unknown"),
                    "risk": state.alias_risks.get(alias, 1),
                }
                for alias, real in state.alias_to_real.items()
            ]

    def get_local_mapping(self, scope: Union[Scope, str]) -> Dict[str, str]:
        """Return a local-only alias snapshot for trusted evaluation code.

        This method is intentionally separate from sanitization APIs. The
        returned mapping must never be included in prompts, telemetry sent to
        an external provider, or attacker-visible logs.
        """

        state = self._state(scope)
        with self._lock:
            return dict(state.alias_to_real)

    def get_alias(self, asset: str, scope: Union[Scope, str]) -> str:
        """Expose an alias only to local adapters/tests, never to the external call."""

        state = self._state(scope)
        with self._lock:
            alias = state.real_to_alias.get(self._mapping_key("asset", asset))
            if alias is None:
                alias = self._register_asset(state, asset)
            return alias
