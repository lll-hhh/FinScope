"""Empirical-risk disclosure and handle rotation for long financial tasks.

Qwen attack outcomes are measured offline and stored as a deterministic
lookup table. The online controller only performs table lookup/interpolation
over local exposure state; it never trains or runs a risk prediction model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .privacy_agent import DisclosureLevel


FEATURE_NAMES = (
    "alias_occurrences",
    "age_days",
    "visible_roles",
    "market_events",
    "trade_events",
    "distinct_assets",
    "high_risk_events",
)


@dataclass
class ExposureState:
    """Local-only summary of what an outside model has observed."""

    alias_occurrences: int = 0
    age_days: int = 0
    visible_roles: set[str] = field(default_factory=set)
    market_events: int = 0
    trade_events: int = 0
    distinct_assets: set[str] = field(default_factory=set)
    high_risk_events: int = 0

    def update(
        self,
        *,
        alias_occurrences: int = 0,
        elapsed_days: int = 0,
        visible_roles: Iterable[str] = (),
        market_events: int = 0,
        trade_events: int = 0,
        assets: Iterable[str] = (),
        high_risk_events: int = 0,
    ) -> None:
        self.alias_occurrences += max(0, int(alias_occurrences))
        self.age_days = max(self.age_days, int(elapsed_days))
        self.visible_roles.update(str(role) for role in visible_roles if str(role))
        self.market_events += max(0, int(market_events))
        self.trade_events += max(0, int(trade_events))
        self.distinct_assets.update(str(asset) for asset in assets if str(asset))
        self.high_risk_events += max(0, int(high_risk_events))

    def reset(self) -> None:
        self.alias_occurrences = 0
        self.age_days = 0
        self.visible_roles.clear()
        self.market_events = 0
        self.trade_events = 0
        self.distinct_assets.clear()
        self.high_risk_events = 0

    def features(self) -> Tuple[float, ...]:
        # Caps make heterogeneous exposure counters comparable in the lookup index.
        return (
            min(self.alias_occurrences, 100) / 100.0,
            min(self.age_days, 365) / 365.0,
            min(len(self.visible_roles), 16) / 16.0,
            min(self.market_events, 100) / 100.0,
            min(self.trade_events, 100) / 100.0,
            min(len(self.distinct_assets), 100) / 100.0,
            min(self.high_risk_events, 100) / 100.0,
        )

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "alias_occurrences": self.alias_occurrences,
            "age_days": self.age_days,
            "visible_roles": sorted(self.visible_roles),
            "market_events": self.market_events,
            "trade_events": self.trade_events,
            "distinct_assets": sorted(self.distinct_assets),
            "high_risk_events": self.high_risk_events,
        }


@dataclass(frozen=True)
class TaskDependencyState:
    """Whether unfinished work still refers to the current external handle."""

    pending_conclusion: bool = False
    pending_risk_judgement: bool = False
    pending_action: bool = False

    @property
    def active(self) -> bool:
        return self.pending_conclusion or self.pending_risk_judgement or self.pending_action


@dataclass(frozen=True)
class RiskEstimate:
    reid_at_1: float
    link_auc: float

    @property
    def combined(self) -> float:
        # Link AUC is centred at 0.5 for random guessing.
        link_risk = max(0.0, min(1.0, 2.0 * abs(self.link_auc - 0.5)))
        return max(self.reid_at_1, link_risk)


@dataclass(frozen=True)
class AttackObservation:
    """One labelled attack result used only during offline calibration."""

    features: Tuple[float, ...]
    reid_at_1: float
    link_auc: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "AttackObservation":
        state = row.get("exposure_state", row.get("state", row))
        if not isinstance(state, Mapping):
            state = {}
        values = []
        for name in FEATURE_NAMES:
            value = state.get(name, 0)
            if name in {"visible_roles", "distinct_assets"}:
                value = len(value) if isinstance(value, (list, tuple, set)) else int(value or 0)
                cap = 16 if name == "visible_roles" else 100
            else:
                cap = {"age_days": 365}.get(name, 100)
            values.append(min(max(float(value), 0.0), float(cap)) / cap)
        return cls(
            tuple(values),
            max(0.0, min(1.0, float(row.get("reid_at_1", row.get("reid", 0.0))))),
            max(0.0, min(1.0, float(row.get("link_auc", 0.5)))),
        )


def _exposure_index(features: Sequence[float]) -> float:
    """Equal-weight index used only to address the empirical lookup table."""

    if len(features) != len(FEATURE_NAMES):
        raise ValueError("exposure feature vector has the wrong length")
    return sum(max(0.0, min(1.0, float(value))) for value in features) / len(features)


class EmpiricalRiskLookup:
    """Piecewise-linear lookup over measured K4 attack outcomes.

    Rows are ordered by their fixed equal-weight exposure index. Repeated
    indices are collapsed conservatively and the cumulative upper envelope is
    used so that additional exposure cannot reduce the online risk. This is a
    deterministic table construction, not model fitting.
    """

    def __init__(self, observations: Sequence[AttackObservation] = ()) -> None:
        grouped: dict[float, RiskEstimate] = {}
        for observation in observations:
            index = _exposure_index(observation.features)
            current = grouped.get(index, RiskEstimate(0.0, 0.5))
            link_risk = max(
                2.0 * abs(current.link_auc - 0.5),
                2.0 * abs(observation.link_auc - 0.5),
            )
            grouped[index] = RiskEstimate(
                max(current.reid_at_1, observation.reid_at_1),
                0.5 + 0.5 * min(1.0, link_risk),
            )
        points: List[Tuple[float, RiskEstimate]] = []
        max_reid = 0.0
        max_link_risk = 0.0
        for index, measured in sorted(grouped.items()):
            max_reid = max(max_reid, measured.reid_at_1)
            max_link_risk = max(max_link_risk, 2.0 * abs(measured.link_auc - 0.5))
            points.append(
                (index, RiskEstimate(max_reid, 0.5 + 0.5 * min(1.0, max_link_risk)))
            )
        self._points = tuple(points)
        self.observation_count = len(observations)

    @property
    def ready(self) -> bool:
        return bool(self._points)

    @property
    def points(self) -> Tuple[Tuple[float, RiskEstimate], ...]:
        return self._points

    def predict(self, state: ExposureState) -> RiskEstimate:
        if not self._points:
            return RiskEstimate(0.0, 0.5)
        target = _exposure_index(state.features())
        left_index = 0.0
        left = RiskEstimate(0.0, 0.5)
        for right_index, right in self._points:
            if target <= right_index:
                width = right_index - left_index
                ratio = 1.0 if width <= 1e-12 else (target - left_index) / width
                ratio = max(0.0, min(1.0, ratio))
                return RiskEstimate(
                    left.reid_at_1 + ratio * (right.reid_at_1 - left.reid_at_1),
                    left.link_auc + ratio * (right.link_auc - left.link_auc),
                )
            left_index, left = right_index, right
        return left


@dataclass(frozen=True)
class DevPolicyResult:
    threshold: float
    utility_loss: float
    reid_at_1: float
    link_auc: float
    eligible: bool = True

    @property
    def privacy_risk(self) -> float:
        return max(self.reid_at_1, 2.0 * abs(self.link_auc - 0.5))


def calibrate_threshold(
    results: Sequence[DevPolicyResult],
    *,
    max_utility_loss: float,
) -> float:
    """Select T on development results under an explicit utility constraint."""

    if not results:
        raise ValueError("development policy results are required")
    eligible = [
        item for item in results
        if item.eligible and item.utility_loss <= max_utility_loss
    ]
    if not eligible:
        raise ValueError("no threshold satisfies the utility constraint")
    selected = min(eligible, key=lambda item: (item.privacy_risk, item.threshold))
    return float(selected.threshold)


class ReplacementDecision(str, Enum):
    KEEP = "keep"
    REPLACE_NOW = "replace_now"
    REPLACE_AT_CHECKPOINT = "replace_at_checkpoint"


@dataclass(frozen=True)
class AdaptiveDecision:
    decision: ReplacementDecision
    level: DisclosureLevel
    risk: RiskEstimate
    reason: str


@dataclass(frozen=True)
class SessionReset:
    """Description of a local-only session reset."""

    old_scope_id: str
    new_scope_id: str
    minimal_state: Mapping[str, Any]


class AdaptiveReplacementController:
    """Online controller for dynamic P-level and handle replacement."""

    def __init__(
        self,
        risk_lookup: EmpiricalRiskLookup,
        *,
        threshold: float,
        default_level: Union[DisclosureLevel, str, int] = DisclosureLevel.P1,
    ) -> None:
        if not 0.0 <= float(threshold) <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.risk_lookup = risk_lookup
        self.threshold = float(threshold)
        self.default_level = DisclosureLevel.parse(default_level)
        self.exposure = ExposureState()
        self.dependencies = TaskDependencyState()
        self.scope_id = ""
        self.rotation_count = 0

    def bind_scope(self, scope_id: str) -> None:
        self.scope_id = str(scope_id)

    def choose_level(
        self,
        *,
        purpose: str = "analysis",
        task_phase: str = "analysis",
        field_risk: int = 1,
    ) -> DisclosureLevel:
        estimate = self.risk_lookup.predict(self.exposure)
        score = estimate.combined
        # P5 is strongest protection. Execution and high-risk fields override
        # a low cumulative score.
        if task_phase.casefold() in {"execution", "trade", "order"} or field_risk >= 4:
            return DisclosureLevel.P5
        if field_risk >= 3 or score >= 0.70:
            selected = DisclosureLevel.P4
        elif field_risk >= 2 or score >= 0.45:
            selected = DisclosureLevel.P3
        elif score >= 0.20:
            selected = DisclosureLevel.P2
        else:
            selected = DisclosureLevel.P1
        # ``default_level`` is a caller-selected protection floor.  Taking
        # the maximum preserves monotonicity even when deployments choose a
        # stricter floor than P1.
        return max(self.default_level, selected)

    def observe_call(
        self,
        *,
        alias_occurrences: int = 1,
        elapsed_days: int = 0,
        visible_roles: Iterable[str] = (),
        market_events: int = 0,
        trade_events: int = 0,
        assets: Iterable[str] = (),
        high_risk_events: int = 0,
        dependencies: Optional[TaskDependencyState] = None,
        safe_checkpoint: bool = False,
        task_phase: str = "analysis",
        field_risk: int = 1,
        purpose: str = "analysis",
    ) -> AdaptiveDecision:
        self.exposure.update(
            alias_occurrences=alias_occurrences,
            elapsed_days=elapsed_days,
            visible_roles=visible_roles,
            market_events=market_events,
            trade_events=trade_events,
            assets=assets,
            high_risk_events=high_risk_events,
        )
        if dependencies is not None:
            self.dependencies = dependencies
        risk = self.risk_lookup.predict(self.exposure)
        level = self.choose_level(purpose=purpose, task_phase=task_phase, field_risk=field_risk)
        if risk.combined < self.threshold:
            return AdaptiveDecision(ReplacementDecision.KEEP, level, risk, "risk_below_T")
        if not self.dependencies.active:
            return AdaptiveDecision(ReplacementDecision.REPLACE_NOW, level, risk, "risk_above_T_no_dependency")
        if safe_checkpoint:
            return AdaptiveDecision(ReplacementDecision.REPLACE_NOW, level, risk, "risk_above_T_at_checkpoint")
        return AdaptiveDecision(
            ReplacementDecision.REPLACE_AT_CHECKPOINT,
            level,
            risk,
            "risk_above_T_pending_dependency",
        )

    def rotated(self, new_scope_id: str) -> None:
        if not self.scope_id:
            raise ValueError("bind_scope must be called before rotation")
        self.scope_id = str(new_scope_id)
        self.exposure.reset()
        self.dependencies = TaskDependencyState()
        self.rotation_count += 1

    def reset_session(
        self,
        new_scope_id: str,
        minimal_state: Mapping[str, Any],
    ) -> SessionReset:
        def contains_alias(value: Any) -> bool:
            if isinstance(value, str):
                return "FS_" in value
            if isinstance(value, Mapping):
                return any(contains_alias(key) or contains_alias(item) for key, item in value.items())
            if isinstance(value, (list, tuple, set)):
                return any(contains_alias(item) for item in value)
            return False

        if contains_alias(minimal_state):
            raise ValueError("minimal session state must not contain old aliases")
        old_scope = self.scope_id
        self.rotated(new_scope_id)
        return SessionReset(old_scope, str(new_scope_id), dict(minimal_state))


class AdaptiveRuntime:
    """Glue the controller to ``LocalPrivacyAgent`` and scope rotation.

    The runtime never sends a mapping to the external model. It closes the old
    scope before opening a new one, then accepts only an alias-free local
    summary as the new session context.
    """

    def __init__(self, agent: Any, controller: AdaptiveReplacementController) -> None:
        self.agent = agent
        self.controller = controller

    def prepare(
        self,
        payload: Any,
        scope: Any,
        *,
        purpose: str = "analysis",
        task_phase: str = "analysis",
        field_risk: int = 1,
        recipient: str = "external-llm",
    ) -> Tuple[Any, DisclosureLevel]:
        self.controller.bind_scope(scope.id)
        level = self.controller.choose_level(
            purpose=purpose, task_phase=task_phase, field_risk=field_risk
        )
        return (
            self.agent.sanitize(
                payload,
                scope,
                disclosure_level=level,
                purpose=purpose,
                recipient=recipient,
            ),
            level,
        )

    def observe_external_call(self, scope: Any, **kwargs: Any) -> AdaptiveDecision:
        self.controller.bind_scope(scope.id)
        return self.controller.observe_call(**kwargs)

    def rotate_at_checkpoint(
        self,
        scope: Any,
        minimal_state: Mapping[str, Any],
        *,
        trading_day: Optional[str] = None,
    ) -> Tuple[Any, SessionReset]:
        new_scope = None
        self.agent.close_scope(scope)
        try:
            new_scope = self.agent.open_scope(
                scope.task_id,
                trading_day or scope.trading_day,
                conversation_id=scope.conversation_id,
                privacy_level=scope.privacy_level,
            )
            reset = self.controller.reset_session(new_scope.id, minimal_state)
            return new_scope, reset
        except Exception:
            if new_scope is not None:
                try:
                    self.agent.close_scope(new_scope)
                except Exception:
                    pass
            raise


def build_empirical_risk_lookup(
    rows: Sequence[Mapping[str, Any]],
) -> EmpiricalRiskLookup:
    """Build a deterministic lookup from measured attack rows."""

    observations = [AttackObservation.from_mapping(row) for row in rows]
    if not observations:
        raise ValueError("at least one attack observation is required")
    return EmpiricalRiskLookup(observations)


def load_empirical_risk_lookup(path: Union[str, Path]) -> EmpiricalRiskLookup:
    """Load measured K4 rows from an empirical calibration artifact."""

    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("calibration artifact must contain a JSON row list")
    return build_empirical_risk_lookup(
        [row for row in rows if isinstance(row, Mapping)]
    )
