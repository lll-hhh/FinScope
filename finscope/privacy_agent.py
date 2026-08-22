"""Local privacy agent for semantic disclosure and audited restoration.

The language model is an untrusted planner and auditor.  The local security
master owns facts, the mediator owns identity bindings, and executable actions
are restored only by deterministic code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from html import escape, unescape
import json
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Dict, List, Optional, Tuple, Union

from .core import ActionValidationError, FinScopeMediator, Scope, ValidationResult
from .recognizer import JsonModelEntityRecognizer


JsonValue = Any


class DisclosureLevel(IntEnum):
    """P1 preserves the most semantics; P5 reveals the least."""

    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    P5 = 5

    @classmethod
    def parse(cls, value: Union["DisclosureLevel", str, int]) -> "DisclosureLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized.isdigit():
                normalized = "P" + normalized
            try:
                return cls[normalized]
            except KeyError as exc:
                raise ValueError("unknown disclosure level %r" % value) from exc
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown disclosure level %r" % value) from exc


@dataclass(frozen=True)
class AssetProfile:
    canonical_id: str
    name: str
    aliases: Tuple[str, ...] = ()
    asset_type: str = "股票"
    market: str = ""
    sector_l1: str = ""
    sector_l2: str = ""
    sector_l3: str = ""
    size_bucket: str = ""
    liquidity_bucket: str = ""
    risk_bucket: str = ""
    themes: Tuple[str, ...] = ()
    version: str = "1"

    @classmethod
    def from_catalog_entry(
        cls, entry: Union[str, Mapping[str, Any]], index: int
    ) -> "AssetProfile":
        if isinstance(entry, str):
            return cls(canonical_id=entry, name=entry)
        name = entry.get("name") or entry.get("symbol") or entry.get("ticker")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("asset catalog entries require a non-empty name")
        aliases = entry.get("aliases", ())
        if isinstance(aliases, str):
            aliases = (aliases,)
        themes = entry.get("themes", ())
        if isinstance(themes, str):
            themes = (themes,)
        canonical_id = entry.get("canonical_id") or entry.get("symbol") or entry.get("ticker")
        return cls(
            canonical_id=str(canonical_id or "%s:%s" % (index, name)).strip(),
            name=name.strip(),
            aliases=tuple(str(item).strip() for item in aliases if str(item).strip()),
            asset_type=str(entry.get("asset_type") or "股票").strip(),
            market=str(entry.get("market") or "").strip(),
            sector_l1=str(entry.get("sector_l1") or entry.get("industry") or "").strip(),
            sector_l2=str(entry.get("sector_l2") or "").strip(),
            sector_l3=str(entry.get("sector_l3") or "").strip(),
            size_bucket=str(entry.get("size_bucket") or "").strip(),
            liquidity_bucket=str(entry.get("liquidity_bucket") or "").strip(),
            risk_bucket=str(entry.get("risk_bucket") or "").strip(),
            themes=tuple(str(item).strip() for item in themes if str(item).strip()),
            version=str(entry.get("version") or "1"),
        )

    def identifiers(self) -> Tuple[str, ...]:
        return (self.name, self.canonical_id) + self.aliases

    def attributes(self) -> Dict[str, str]:
        return {
            "asset_type": self.asset_type,
            "market": self.market,
            "sector_l1": self.sector_l1,
            "sector_l2": self.sector_l2,
            "sector_l3": self.sector_l3,
            "size_bucket": self.size_bucket,
            "liquidity_bucket": self.liquidity_bucket,
            "risk_bucket": self.risk_bucket,
        }


@dataclass(frozen=True)
class DisclosureCandidate:
    level: DisclosureLevel
    descriptor: str
    used_attributes: Tuple[str, ...]
    source: str = "deterministic"


@dataclass(frozen=True)
class DisclosurePlan:
    canonical_id: str
    candidates: Tuple[DisclosureCandidate, ...]

    def at(self, level: Union[DisclosureLevel, str, int]) -> DisclosureCandidate:
        wanted = DisclosureLevel.parse(level)
        for candidate in self.candidates:
            if candidate.level == wanted:
                return candidate
        raise KeyError("plan has no candidate for %s" % wanted.name)


@dataclass(frozen=True)
class BindingRecord:
    scope_id: str
    alias: str
    canonical_id: str
    entity_type: str
    disclosure_level: str
    descriptor: str
    purpose: str
    recipient: str
    source: str

    @property
    def surface(self) -> str:
        return '<fin-ref type="%s" id="%s">%s</fin-ref>' % (
            self.entity_type,
            self.alias,
            escape(self.descriptor, quote=False),
        )


@dataclass(frozen=True)
class AuditIssue:
    code: str
    severity: str
    message: str
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RestorationResult:
    value: JsonValue
    status: str
    issues: Tuple[AuditIssue, ...] = ()

    @property
    def safe(self) -> bool:
        return self.status == "safe"


class AmbiguousRestorationError(ActionValidationError):
    """Raised when an executable result cannot be restored unambiguously."""


class DeterministicDisclosurePlanner:
    """Safe fallback derived only from the local security master."""

    LEVEL_FIELDS = {
        DisclosureLevel.P1: ("size_bucket", "sector_l3", "asset_type"),
        DisclosureLevel.P2: ("sector_l3", "sector_l2", "asset_type"),
        DisclosureLevel.P3: ("sector_l1", "asset_type"),
        DisclosureLevel.P4: ("market", "asset_type"),
        DisclosureLevel.P5: ("asset_type",),
    }

    def plan(self, profile: AssetProfile, purpose: str = "analysis") -> DisclosurePlan:
        attributes = profile.attributes()
        candidates: List[DisclosureCandidate] = []
        for level in DisclosureLevel:
            values: List[str] = []
            used: List[str] = []
            for key in self.LEVEL_FIELDS[level]:
                value = attributes.get(key, "")
                if value and value not in values:
                    values.append(value)
                    used.append(key)
                if level == DisclosureLevel.P2 and key in {"sector_l3", "sector_l2"} and value:
                    # Use the most specific available sector, not two nested labels.
                    break
            if level == DisclosureLevel.P2 and values:
                asset_type = attributes.get("asset_type", "")
                if asset_type and asset_type not in values:
                    values.append(asset_type)
                    used.append("asset_type")
            if not values:
                values = ["金融标的"]
            elif values == [profile.asset_type] and level == DisclosureLevel.P5:
                values = [profile.asset_type or "金融标的"]
            descriptor = "".join(values)
            forbidden = tuple(
                item.casefold() for item in profile.identifiers() if item
            )
            if any(item in descriptor.casefold() for item in forbidden):
                if len(values) > 1:
                    descriptor = values[0] + "类" + "".join(values[1:])
                if any(item in descriptor.casefold() for item in forbidden):
                    descriptor = profile.asset_type or "金融标的"
                    used = ["asset_type"] if profile.asset_type else []
                if any(item in descriptor.casefold() for item in forbidden):
                    descriptor = "金融标的"
                    used = []
            candidates.append(
                DisclosureCandidate(level, descriptor, tuple(used), "deterministic")
            )
        return DisclosurePlan(profile.canonical_id, tuple(candidates))


class JsonModelDisclosurePlanner:
    """Ask a local model for five descriptions, then validate every claim."""

    def __init__(
        self,
        model_call: Callable[[str], str],
        *,
        fallback: Optional[DeterministicDisclosurePlanner] = None,
        max_descriptor_length: int = 48,
        allow_fallback: bool = True,
    ) -> None:
        self.model_call = model_call
        self.fallback = fallback or DeterministicDisclosurePlanner()
        self.max_descriptor_length = max_descriptor_length
        self.allow_fallback = allow_fallback
        self._cache: Dict[Tuple[str, str, str], DisclosurePlan] = {}
        self._lock = threading.RLock()
        self.calls = 0
        self.successes = 0
        self.fallbacks = 0
        self.repairs = 0

    def plan(self, profile: AssetProfile, purpose: str = "analysis") -> DisclosurePlan:
        cache_key = (profile.canonical_id, profile.version, purpose)
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
            fallback = self.fallback.plan(profile, purpose)
            prompt = self._prompt(profile, purpose)
            # Strict runs may retry transiently truncated or malformed JSON,
            # but never substitute the deterministic plan as a successful
            # model result. Three attempts bounds both latency and cost.
            attempts = 3 if not self.allow_fallback else 1
            last_error: Optional[Exception] = None
            for _ in range(attempts):
                self.calls += 1
                try:
                    payload = self._parse_json(self.model_call(prompt))
                    proposed = self._validate(payload, profile, fallback)
                    if proposed is fallback:
                        last_error = ValueError(
                            "local disclosure model did not produce a complete valid plan"
                        )
                        continue
                except Exception as exc:
                    last_error = exc
                    continue
                self.successes += 1
                if any(
                    candidate.source == "local-model-field-normalized"
                    for candidate in proposed.candidates
                ):
                    self.repairs += 1
                self._cache[cache_key] = proposed
                return proposed
            if not self.allow_fallback:
                self.fallbacks += 1
                if last_error is not None:
                    raise last_error
                raise ValueError(
                    "local disclosure model did not produce a complete valid plan"
                )
            self.fallbacks += 1
            self._cache[cache_key] = fallback
            return fallback

    def _prompt(self, profile: AssetProfile, purpose: str) -> str:
        safe_profile = profile.attributes()
        master_lines = "\n".join(
            "%s=%s" % (key, value or "(空)")
            for key, value in safe_profile.items()
        )
        return (
            "你是本地金融隐私规划器，也是严格JSON复制器。只输出JSON对象，不要解释。"
            "必须返回P1、P2、P3、P4、P5恰好五项。禁止改写、概括或替换字段值，"
            "尤其不能把sector_l1的值用于sector_l3。每个descriptor必须等于"
            "used_attributes按列表顺序对应的字段值直接拼接；used_attributes只能列出"
            "确实拼接进descriptor的字段。字段为空或与已使用字段重复时可以省略，但"
            "不能列出省略的字段。允许字段顺序：P1=size_bucket,sector_l3,asset_type；"
            "P2=sector_l3,asset_type；P3=sector_l1,asset_type；"
            "P4=market,asset_type；P5=asset_type。\n"
            "SECURITY_MASTER字段（只能复制这些值）：\n%s\n"
            "PURPOSE=%s\n输出格式：{\"candidates\":["
            "{\"level\":\"P1\",\"descriptor\":\"字段值拼接\",\"used_attributes\":[\"字段名\"]},"
            "{\"level\":\"P2\",\"descriptor\":\"字段值拼接\",\"used_attributes\":[\"字段名\"]},"
            "{\"level\":\"P3\",\"descriptor\":\"字段值拼接\",\"used_attributes\":[\"字段名\"]},"
            "{\"level\":\"P4\",\"descriptor\":\"字段值拼接\",\"used_attributes\":[\"字段名\"]},"
            "{\"level\":\"P5\",\"descriptor\":\"字段值拼接\",\"used_attributes\":[\"字段名\"]}]}\nJSON="
            % (master_lines, purpose)
        )

    @staticmethod
    def _parse_json(raw: str) -> Mapping[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        decoder = json.JSONDecoder()
        payload = None
        for match in re.finditer(r"\{", text):
            try:
                candidate, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, Mapping):
                payload = candidate
                break
        if not isinstance(payload, Mapping):
            raise ValueError("planner response must be a JSON object")
        return payload

    def _validate(
        self,
        payload: Mapping[str, Any],
        profile: AssetProfile,
        fallback: DisclosurePlan,
    ) -> DisclosurePlan:
        rows = payload.get("candidates")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return fallback
        by_level: Dict[DisclosureLevel, DisclosureCandidate] = {}
        attributes = profile.attributes()
        forbidden = tuple(item.casefold() for item in profile.identifiers() if item)
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            try:
                level = DisclosureLevel.parse(row.get("level"))
            except ValueError:
                continue
            descriptor = row.get("descriptor")
            used = row.get("used_attributes", ())
            if not isinstance(descriptor, str) or not isinstance(used, Sequence):
                continue
            descriptor = descriptor.strip()
            # Small local models occasionally insert spaces between Latin and
            # CJK tokens (for example ``A 股`` for the master value ``A股``).
            # Whitespace is presentation-only here; all substantive claims
            # remain checked against the exact security-master attributes.
            compact_descriptor = re.sub(r"\s+", "", descriptor)
            allowed = set(self.fallback.LEVEL_FIELDS[level])
            # Treat the model's field list as an untrusted proposal. Keep only
            # fields allowed for this disclosure level, remove duplicates and
            # empty master values, then rebuild the descriptor from the
            # surviving security-master facts.
            proposed_keys = tuple(str(item) for item in used)
            used_keys = tuple(
                dict.fromkeys(
                    key
                    for key in proposed_keys
                    if key in allowed and attributes.get(key)
                )
            )
            if (
                not descriptor
                or len(descriptor) > self.max_descriptor_length
                or any(
                    re.sub(r"\s+", "", token) in compact_descriptor.casefold()
                    for token in forbidden
                )
                or not used_keys
                or any(mark in descriptor for mark in ("<", ">", "FS_"))
            ):
                continue
            expected_descriptor = "".join(attributes[key] for key in used_keys)
            compact_expected = re.sub(r"\s+", "", expected_descriptor)
            source = "local-model"
            if compact_descriptor != compact_expected:
                # The model may select the right master fields but mis-copy or
                # reorder their surface text. Normalize only from those
                # validated fields; never use a full deterministic plan.
                descriptor = expected_descriptor
                source = "local-model-field-normalized"
            by_level[level] = DisclosureCandidate(
                level, descriptor, used_keys, source
            )
        if len(by_level) != len(DisclosureLevel):
            return fallback
        return DisclosurePlan(
            profile.canonical_id,
            tuple(by_level[level] for level in DisclosureLevel),
        )


@dataclass(frozen=True)
class EmpiricalDisclosurePolicy:
    """An adaptive policy calibrated from completed experiments."""

    levels_by_purpose: Mapping[str, Union[DisclosureLevel, str, int]]
    fallback: Union[DisclosureLevel, str, int] = DisclosureLevel.P5
    calibrated_on: str = ""

    def choose(self, purpose: str, recipient: str = "external-llm") -> DisclosureLevel:
        value = self.levels_by_purpose.get(
            "%s:%s" % (purpose, recipient),
            self.levels_by_purpose.get(purpose, self.fallback),
        )
        return DisclosureLevel.parse(value)


class JsonModelRecoveryAuditor:
    """Optional local semantic auditor. It can report but never mutate bindings."""

    ALLOWED_CODES = frozenset(
        {
            "coreference_ambiguity",
            "semantic_drift",
            "missing_handle",
            "contradictory_action",
            "incomplete_output",
        }
    )

    def __init__(self, model_call: Callable[[str], str]) -> None:
        self.model_call = model_call
        self.calls = 0
        self.failures = 0

    def audit(
        self,
        external_value: JsonValue,
        restored_value: JsonValue,
        bindings: Sequence[BindingRecord],
    ) -> Tuple[AuditIssue, ...]:
        binding_summary = [
            {"id": item.alias, "description": item.descriptor, "type": item.entity_type}
            for item in bindings
        ]
        prompt = (
            "你是本地恢复审计器。只检查外部结果与本地恢复结果是否存在指代歧义、"
            "语义漂移、缺少句柄、动作矛盾或输出不完整。不要评价投资决策，不得推断"
            "真实资产，不得修复文本或编造问题。没有问题时只输出{\"issues\":[]}。"
            "本地恢复结果中出现安全主表里的真实名称是预期行为，不算missing_handle；"
            "FS_ACTION、FS_ACCOUNT、FS_REF等非资产本地句柄也可以由确定性代码恢复，"
            "不算missing_handle。只有外部可执行字段把资产语义描述或真实资产名裸露在"
            "句柄之外，或句柄与本地绑定不一致时，才报告missing_handle。外部的"
            "<fin-ref type=asset id=FS_...>描述</fin-ref>与本地恢复后的真实名称对应"
            "是正常闭环。"
            "有问题时code只允许coreference_ambiguity、semantic_drift、missing_handle、"
            "contradictory_action、incomplete_output，severity只允许warning或error。"
            "只输出合法JSON对象，不要Markdown。\n"
            "BINDINGS: %s\nEXTERNAL: %s\nRESTORED: %s"
            % (
                json.dumps(binding_summary, ensure_ascii=False),
                json.dumps(external_value, ensure_ascii=False),
                json.dumps(restored_value, ensure_ascii=False),
            )
        )
        self.calls += 1
        try:
            payload = JsonModelDisclosurePlanner._parse_json(self.model_call(prompt))
        except Exception:
            self.failures += 1
            return (
                AuditIssue(
                    "auditor_failure",
                    "warning",
                    "local semantic auditor returned an invalid response",
                ),
            )
        issues: List[AuditIssue] = []
        for row in payload.get("issues", ()):
            if not isinstance(row, Mapping) or row.get("code") not in self.ALLOWED_CODES:
                continue
            severity = row.get("severity")
            if severity not in {"warning", "error"}:
                continue
            aliases = row.get("aliases", ())
            if not isinstance(aliases, Sequence) or isinstance(aliases, (str, bytes)):
                aliases = ()
            issues.append(
                AuditIssue(
                    str(row["code"]),
                    severity,
                    str(row.get("message") or row["code"])[:256],
                    tuple(str(item).upper() for item in aliases),
                )
            )
        return tuple(issues)


@dataclass
class _AgentScopeState:
    bindings: List[BindingRecord] = field(default_factory=list)
    metrics: Dict[str, int] = field(
        default_factory=lambda: {
            "disclosure_plans_created": 0,
            "semantic_bindings_issued": 0,
            "restoration_audits": 0,
            "restoration_rejections": 0,
            "semantic_auditor_calls": 0,
        }
    )


class LocalPrivacyAgent:
    """Model-assisted privacy agent with code-owned identity restoration."""

    _ALIAS_PATTERN = re.compile(
        r"(?<![A-Za-z0-9_])FS_(?:ASSET|ORG|PORTFOLIO|STRATEGY|ACCOUNT|REF|ACTION|REL|INTENT)_"
        r"[A-Z2-9]{8}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    _WRAPPER_PATTERN = re.compile(
        r'<fin-ref\s+type="(?P<type>[a-z_]+)"\s+id="(?P<alias>FS_[A-Z_]+_[A-Z2-9]{8})">'
        r"(?P<descriptor>.*?)</fin-ref>",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(
        self,
        asset_catalog: Sequence[Union[str, Mapping[str, Any]]],
        *,
        mediator: Optional[FinScopeMediator] = None,
        disclosure_planner: Optional[Any] = None,
        recovery_auditor: Optional[JsonModelRecoveryAuditor] = None,
        default_level: Union[DisclosureLevel, str, int] = DisclosureLevel.P5,
        adaptive_policy: Optional[EmpiricalDisclosurePolicy] = None,
    ) -> None:
        self.mediator = mediator or FinScopeMediator(asset_catalog)
        self.disclosure_planner = disclosure_planner or DeterministicDisclosurePlanner()
        self.recovery_auditor = recovery_auditor
        self.default_level = DisclosureLevel.parse(default_level)
        self.adaptive_policy = adaptive_policy
        self._lock = threading.RLock()
        self._states: Dict[str, _AgentScopeState] = {}
        self._profiles: Dict[str, AssetProfile] = {}
        for index, entry in enumerate(asset_catalog):
            profile = AssetProfile.from_catalog_entry(entry, index)
            for identifier in profile.identifiers():
                self._profiles[self._normalize(identifier)] = profile

    def open_scope(self, task_id: str, trading_day: str, **kwargs: Any) -> Scope:
        scope = self.mediator.open_scope(task_id, trading_day, **kwargs)
        with self._lock:
            self._states.setdefault(scope.id, _AgentScopeState())
        return scope

    def close_scope(self, scope: Union[Scope, str]) -> None:
        scope_id = scope.id if isinstance(scope, Scope) else scope
        with self._lock:
            self._states.pop(scope_id, None)
        self.mediator.close_scope(scope)

    def sanitize(
        self,
        payload: JsonValue,
        scope: Union[Scope, str],
        *,
        disclosure_level: Optional[Union[DisclosureLevel, str, int]] = None,
        purpose: str = "analysis",
        recipient: str = "external-llm",
        adaptive: bool = False,
        force_model_scan: bool = False,
    ) -> JsonValue:
        state = self._agent_state(scope)
        if adaptive:
            if self.adaptive_policy is None:
                raise ValueError(
                    "adaptive disclosure requires a policy calibrated from experiments"
                )
            level = self.adaptive_policy.choose(purpose, recipient)
        else:
            level = DisclosureLevel.parse(disclosure_level or self.default_level)
        sanitized = self.mediator.sanitize(
            payload, scope, force_model_scan=force_model_scan
        )
        aliases_in_payload = set(self._find_aliases(sanitized))
        records = self.mediator.get_mapping_records(scope)
        replacements: Dict[str, str] = {}
        with self._lock:
            for record in records:
                if record["type"] != "asset":
                    continue
                alias = record["alias"].upper()
                if alias not in aliases_in_payload:
                    continue
                profile = self._profiles.get(self._normalize(record["canonical"]))
                if profile is None:
                    profile = AssetProfile(
                        canonical_id=record["canonical"],
                        name=record["canonical"],
                    )
                plan = self.disclosure_planner.plan(profile, purpose)
                candidate = plan.at(level)
                binding = BindingRecord(
                    scope_id=self._scope_id(scope),
                    alias=alias,
                    canonical_id=profile.canonical_id,
                    entity_type="asset",
                    disclosure_level=level.name,
                    descriptor=candidate.descriptor,
                    purpose=purpose,
                    recipient=recipient,
                    source=candidate.source,
                )
                if binding not in state.bindings:
                    state.bindings.append(binding)
                    state.metrics["semantic_bindings_issued"] += 1
                replacements[alias] = binding.surface
            state.metrics["disclosure_plans_created"] = len(
                {(item.canonical_id, item.purpose) for item in state.bindings}
            )
        return self._replace_value(sanitized, replacements)

    def restore_and_audit(
        self,
        output: JsonValue,
        scope: Union[Scope, str],
        *,
        execution: bool = False,
    ) -> RestorationResult:
        state = self._agent_state(scope)
        issues: List[AuditIssue] = []
        known_aliases = {
            record["alias"].upper()
            for record in self.mediator.get_mapping_records(scope)
        }
        binding_by_alias: Dict[str, List[BindingRecord]] = {}
        for binding in state.bindings:
            binding_by_alias.setdefault(binding.alias, []).append(binding)

        def unwrap(text: str, *, require_handle: bool) -> str:
            wrapper_spans: List[Tuple[int, int]] = []
            pieces: List[str] = []
            cursor = 0
            for match in self._WRAPPER_PATTERN.finditer(text):
                pieces.append(text[cursor:match.start()])
                alias = match.group("alias").upper()
                descriptor = unescape(match.group("descriptor"))
                entity_type = match.group("type").casefold()
                wrapper_spans.append((match.start(), match.end()))
                matches = binding_by_alias.get(alias, ())
                if alias not in known_aliases or not matches:
                    issues.append(
                        AuditIssue("unknown_handle", "error", "unknown or stale privacy handle", (alias,))
                    )
                elif not any(
                    item.descriptor == descriptor and item.entity_type == entity_type
                    for item in matches
                ):
                    issues.append(
                        AuditIssue("binding_mismatch", "error", "handle description or type does not match its local binding", (alias,))
                    )
                pieces.append(alias)
                cursor = match.end()
            pieces.append(text[cursor:])
            outside = list(text)
            for start, end in wrapper_spans:
                outside[start:end] = " " * (end - start)
            outside_text = "".join(outside)
            descriptors: Dict[str, set] = {}
            for binding in state.bindings:
                descriptors.setdefault(binding.descriptor, set()).add(binding.alias)
            for descriptor, aliases in descriptors.items():
                if descriptor and descriptor in outside_text:
                    if execution and not require_handle:
                        continue
                    # Bare descriptors in explanatory text are audit evidence,
                    # but only executable fields must carry a recoverable handle.
                    severity = "error" if execution else "warning"
                    issues.append(
                        AuditIssue(
                            "missing_handle",
                            severity,
                            "semantic description appeared without its recoverable handle",
                            tuple(sorted(aliases)),
                        )
                    )
            return "".join(pieces)

        def unwrap_value(value: JsonValue, key_hint: str = "") -> JsonValue:
            if isinstance(value, str):
                require_handle = execution and (
                    not key_hint
                    or key_hint.casefold() in self.mediator.ASSET_FIELD_NAMES
                )
                return unwrap(value, require_handle=require_handle)
            if isinstance(value, Mapping):
                return {
                    key: unwrap_value(item, str(key))
                    for key, item in value.items()
                }
            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                return [unwrap_value(item, key_hint) for item in value]
            return value

        unwrapped = unwrap_value(output)
        for alias in self._find_aliases(unwrapped):
            if alias not in known_aliases:
                issues.append(
                    AuditIssue("unknown_handle", "error", "unknown or stale privacy handle", (alias,))
                )
        external_text = json.dumps(output, ensure_ascii=False) if not isinstance(output, str) else output
        for profile in set(self._profiles.values()):
            if any(
                self._contains_identifier(external_text, identifier)
                for identifier in profile.identifiers()
                if identifier
            ):
                issues.append(
                    AuditIssue("direct_identity_output", "error", "external output contains a real asset identifier")
                )
                break
        restored = self.mediator.restore_output(unwrapped, scope)
        if self.recovery_auditor is not None:
            # Handle presence and binding integrity are code-owned checks. A
            # small advisory model often describes the expected
            # handle-to-canonical restoration as a "missing handle"; accept
            # that issue only when the deterministic pass found the same
            # structural defect. Other semantic findings remain advisory.
            audited_issues = self.recovery_auditor.audit(
                output, restored, state.bindings
            )
            deterministic_missing_handle = any(
                item.code == "missing_handle" for item in issues
            )
            issues.extend(
                item
                for item in audited_issues
                if item.code != "missing_handle" or deterministic_missing_handle
            )
            state.metrics["semantic_auditor_calls"] += 1
        issues = self._deduplicate_issues(issues)
        if any(item.severity == "error" for item in issues):
            status = "rejected"
        elif issues:
            status = "needs_retry"
        else:
            status = "safe"
        state.metrics["restoration_audits"] += 1
        if status == "rejected":
            state.metrics["restoration_rejections"] += 1
        result = RestorationResult(restored, status, tuple(issues))
        if execution and not result.safe:
            raise AmbiguousRestorationError(
                "restoration audit failed: %s" % ", ".join(item.code for item in issues)
            )
        return result

    def validate_action(
        self, action: Mapping[str, Any], scope: Union[Scope, str]
    ) -> ValidationResult:
        result = self.restore_and_audit(action, scope, execution=True)
        if not isinstance(result.value, Mapping):
            raise ActionValidationError("restored action must be a mapping")
        return self.mediator.validate_action(dict(result.value), scope)

    def get_bindings(self, scope: Union[Scope, str]) -> Tuple[BindingRecord, ...]:
        return tuple(self._agent_state(scope).bindings)

    def get_metrics(self, scope: Union[Scope, str]) -> Dict[str, int]:
        metrics = self.mediator.get_metrics(scope)
        metrics.update(self._agent_state(scope).metrics)
        if isinstance(self.disclosure_planner, JsonModelDisclosurePlanner):
            metrics["disclosure_planner_calls"] = self.disclosure_planner.calls
            metrics["disclosure_planner_successes"] = self.disclosure_planner.successes
            metrics["disclosure_planner_fallbacks"] = self.disclosure_planner.fallbacks
            metrics["disclosure_planner_repairs"] = self.disclosure_planner.repairs
        if self.recovery_auditor is not None:
            metrics["recovery_auditor_calls"] = self.recovery_auditor.calls
            metrics["recovery_auditor_failures"] = self.recovery_auditor.failures
        recognizer = self.mediator.entity_recognizer
        if isinstance(recognizer, JsonModelEntityRecognizer):
            metrics["entity_recognizer_model_calls"] = recognizer.calls
            metrics["entity_recognizer_model_failures"] = recognizer.failures
            metrics["entity_recognizer_fallbacks"] = recognizer.fallbacks
        return metrics

    def _agent_state(self, scope: Union[Scope, str]) -> _AgentScopeState:
        scope_id = self._scope_id(scope)
        with self._lock:
            if scope_id not in self._states:
                self._states[scope_id] = _AgentScopeState()
            return self._states[scope_id]

    @staticmethod
    def _scope_id(scope: Union[Scope, str]) -> str:
        return scope.id if isinstance(scope, Scope) else scope

    @classmethod
    def _replace_value(cls, value: JsonValue, replacements: Mapping[str, str]) -> JsonValue:
        if isinstance(value, str):
            return cls._ALIAS_PATTERN.sub(
                lambda match: replacements.get(match.group(0).upper(), match.group(0)), value
            )
        if isinstance(value, Mapping):
            return {
                cls._replace_value(key, replacements) if isinstance(key, str) else key:
                cls._replace_value(item, replacements)
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._replace_value(item, replacements) for item in value]
        return value

    @staticmethod
    def _transform_strings(value: JsonValue, transform: Callable[[str], str]) -> JsonValue:
        if isinstance(value, str):
            return transform(value)
        if isinstance(value, Mapping):
            return {
                transform(key) if isinstance(key, str) else key:
                LocalPrivacyAgent._transform_strings(item, transform)
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [LocalPrivacyAgent._transform_strings(item, transform) for item in value]
        return value

    @classmethod
    def _find_aliases(cls, value: JsonValue) -> Tuple[str, ...]:
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        return tuple(match.group(0).upper() for match in cls._ALIAS_PATTERN.finditer(raw))

    @staticmethod
    def _contains_identifier(text: str, identifier: str) -> bool:
        if not identifier:
            return False
        if (
            identifier[0].isascii()
            and identifier[-1].isascii()
            and (identifier[0].isalnum() or identifier[0] == "_")
            and (identifier[-1].isalnum() or identifier[-1] == "_")
        ):
            pattern = (
                r"(?<![A-Za-z0-9_])"
                + re.escape(identifier)
                + r"(?![A-Za-z0-9_])"
            )
            return re.search(pattern, text, flags=re.IGNORECASE) is not None
        return identifier.casefold() in text.casefold()

    @staticmethod
    def _deduplicate_issues(issues: Sequence[AuditIssue]) -> List[AuditIssue]:
        seen = set()
        result = []
        for issue in issues:
            key = (issue.code, issue.severity, issue.aliases)
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
