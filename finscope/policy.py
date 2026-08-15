"""Adaptive disclosure policy for the local FinScope runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any, Optional, Tuple, Union


class PrivacyLevel(IntEnum):
    """Protection strength used by one FinScope conversation scope."""

    LOW = 1
    STANDARD = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, value: Union["PrivacyLevel", str, int]) -> "PrivacyLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls[value.strip().upper()]
            except KeyError as exc:
                raise ValueError(f"unknown privacy level {value!r}") from exc
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown privacy level {value!r}") from exc


@dataclass(frozen=True)
class PrivacyDecision:
    level: PrivacyLevel
    reasons: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ResidualScanDecision:
    should_scan: bool
    reason: str
    fingerprint: str


class ResidualScanPolicy:
    """Gate local-model calls after residual detection has stabilized.

    ``balanced`` enters cooldown after consecutive empty scans, while still
    waking on risk signals, privacy escalation, and periodic probes.
    ``conservative`` additionally scans every previously unseen template.
    """

    _ALIAS_PATTERN = re.compile(
        r"FS_(?:ASSET|ORG|PORTFOLIO|STRATEGY|ACCOUNT|REF|ACTION|REL|INTENT)_"
        r"[A-Z2-9]{8}",
        re.IGNORECASE,
    )
    _RISK_PATTERNS = (
        re.compile(r"(?<![A-Za-z0-9_])[A-Z]{2,6}(?![A-Za-z0-9_])"),
        re.compile(r"(?<!\d)\d{6}(?!\d)"),
        re.compile(
            r"account|portfolio|holding|position|watchlist|order|trade|"
            r"账户|组合|策略|持仓|候选池|买入|卖出|增持|减持|清仓|调仓",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        *,
        warmup_scans: int = 2,
        no_new_threshold: int = 3,
        probe_interval: int = 10,
        max_safe_templates: int = 2048,
        mode: str = "balanced",
    ) -> None:
        if warmup_scans < 0:
            raise ValueError("warmup_scans cannot be negative")
        if no_new_threshold < 1 or probe_interval < 1 or max_safe_templates < 1:
            raise ValueError("scan thresholds must be positive")
        if mode not in {"balanced", "conservative"}:
            raise ValueError("mode must be 'balanced' or 'conservative'")
        self.warmup_scans = warmup_scans
        self.no_new_threshold = no_new_threshold
        self.probe_interval = probe_interval
        self.max_safe_templates = max_safe_templates
        self.mode = mode

    def decide(
        self,
        text: str,
        *,
        model_calls: int,
        consecutive_empty_scans: int,
        skipped_since_probe: int,
        safe_fingerprints: Sequence[str],
        privacy_level: PrivacyLevel,
        last_scan_level: PrivacyLevel,
        force: bool = False,
    ) -> ResidualScanDecision:
        fingerprint = self.fingerprint(text)
        if force:
            return ResidualScanDecision(True, "forced", fingerprint)
        residual = self._ALIAS_PATTERN.sub(" ", text).strip()
        if not residual:
            return ResidualScanDecision(False, "aliases-only", fingerprint)
        if privacy_level > last_scan_level:
            return ResidualScanDecision(True, "privacy-escalation", fingerprint)
        if any(pattern.search(residual) for pattern in self._RISK_PATTERNS):
            return ResidualScanDecision(True, "risk-signal", fingerprint)
        if model_calls < self.warmup_scans:
            return ResidualScanDecision(True, "warmup", fingerprint)
        if consecutive_empty_scans < self.no_new_threshold:
            return ResidualScanDecision(True, "stabilizing", fingerprint)
        if skipped_since_probe >= self.probe_interval:
            return ResidualScanDecision(True, "periodic-probe", fingerprint)
        if fingerprint in safe_fingerprints:
            return ResidualScanDecision(False, "safe-template", fingerprint)
        if self.mode == "conservative":
            return ResidualScanDecision(True, "unseen-template", fingerprint)
        return ResidualScanDecision(False, "cooldown", fingerprint)

    @classmethod
    def fingerprint(cls, text: str) -> str:
        normalized = cls._ALIAS_PATTERN.sub("<alias>", text)
        normalized = re.sub(r"https?://\S+", "<url>", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", "<num>", normalized)
        normalized = " ".join(normalized.casefold().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class AdaptivePrivacyPolicy:
    """Raise protection when content or cumulative exposure becomes riskier.

    Escalation is monotonic inside one scope. A lower level is available again
    only after a new conversation scope is opened, which also rotates aliases.
    """

    TYPE_ACTIVATION_LEVEL = {
        "asset": PrivacyLevel.LOW,
        "account": PrivacyLevel.LOW,
        "institution": PrivacyLevel.STANDARD,
        "organization": PrivacyLevel.STANDARD,
        "portfolio": PrivacyLevel.STANDARD,
        "strategy": PrivacyLevel.STANDARD,
        "reference": PrivacyLevel.STANDARD,
        "action": PrivacyLevel.HIGH,
        "relation": PrivacyLevel.HIGH,
        "intent": PrivacyLevel.HIGH,
    }
    HIGH_RISK_KEYS = frozenset(
        {
            "holdings",
            "positions",
            "candidate_pool",
            "watchlist",
            "portfolio",
            "portfolio_id",
            "strategy_id",
            "strategy_name",
            "target_weight",
            "allocation",
        }
    )
    CRITICAL_RISK_KEYS = frozenset(
        {
            "account_id",
            "orders",
            "trades",
            "transactions",
            "execution",
            "beneficiary",
        }
    )
    ATTACK_MARKERS = (
        "ignore previous",
        "reveal mapping",
        "真实资产",
        "映射表",
        "系统提示",
        "泄露",
    )

    def __init__(self, *, cumulative_exposure_threshold: int = 4) -> None:
        if cumulative_exposure_threshold < 1:
            raise ValueError("cumulative_exposure_threshold must be positive")
        self.cumulative_exposure_threshold = cumulative_exposure_threshold

    def decide(
        self,
        payload: Any,
        base_level: Union[PrivacyLevel, str, int],
        previous_level: Union[PrivacyLevel, str, int],
        disclosure_count: int,
        requested_level: Optional[Union[PrivacyLevel, str, int]] = None,
    ) -> PrivacyDecision:
        base = PrivacyLevel.parse(base_level)
        previous = PrivacyLevel.parse(previous_level)
        requested = PrivacyLevel.parse(requested_level) if requested_level is not None else base
        level = max(base, previous, requested)
        reasons = []
        keys, strings = self._collect(payload)

        if keys & self.HIGH_RISK_KEYS and level < PrivacyLevel.HIGH:
            level = PrivacyLevel.HIGH
            reasons.append("portfolio-state")
        if keys & self.CRITICAL_RISK_KEYS and level < PrivacyLevel.CRITICAL:
            level = PrivacyLevel.CRITICAL
            reasons.append("execution-state")
        text = "\n".join(strings).casefold()
        if any(marker in text for marker in self.ATTACK_MARKERS):
            if level < PrivacyLevel.CRITICAL:
                level = PrivacyLevel.CRITICAL
            reasons.append("attack-marker")
        if disclosure_count >= self.cumulative_exposure_threshold:
            raised = PrivacyLevel(min(int(level) + 1, int(PrivacyLevel.CRITICAL)))
            if raised > level:
                level = raised
            reasons.append("cumulative-exposure")
        return PrivacyDecision(level=PrivacyLevel(level), reasons=tuple(reasons))

    def protects(
        self,
        entity_type: str,
        level: Union[PrivacyLevel, str, int],
        risk: int = 2,
    ) -> bool:
        activation = self.TYPE_ACTIVATION_LEVEL.get(entity_type.casefold())
        if activation is None:
            return False
        try:
            risk = max(1, min(4, int(risk)))
        except (TypeError, ValueError):
            risk = 2
        # A model-assessed high-risk expression is protected one level earlier.
        if risk >= 3 and activation > PrivacyLevel.LOW:
            activation = PrivacyLevel(int(activation) - 1)
        if risk == 4:
            activation = PrivacyLevel.LOW
        return PrivacyLevel.parse(level) >= activation

    @classmethod
    def _collect(cls, value: Any) -> Tuple[set[str], list[str]]:
        keys: set[str] = set()
        strings: list[str] = []

        def visit(item: Any) -> None:
            if isinstance(item, str):
                strings.append(item)
            elif isinstance(item, Mapping):
                for key, child in item.items():
                    keys.add(str(key).casefold())
                    visit(child)
            elif isinstance(item, Sequence) and not isinstance(
                item, (str, bytes, bytearray)
            ):
                for child in item:
                    visit(child)

        visit(value)
        return keys, strings
