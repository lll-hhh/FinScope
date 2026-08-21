"""Uniform hooks for adding the same privacy parameters to three benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from .core import Scope, ValidationResult
from .privacy_agent import DisclosureLevel, LocalPrivacyAgent, RestorationResult


class BenchmarkName(Enum):
    NLPCC_2026_TASK4 = "nlpcc2026-task4"
    STOCKBENCH = "stockbench"
    FINVAULT = "finvault"


@dataclass(frozen=True)
class EpisodeContext:
    benchmark: BenchmarkName
    episode_id: str
    trading_day: str
    conversation_id: str


@dataclass(frozen=True)
class PrivacyRunConfig:
    method: str = "finscope"
    disclosure_level: DisclosureLevel = DisclosureLevel.P5
    adaptive: bool = False
    purpose: str = "analysis"
    recipient: str = "external-llm"


@dataclass
class TraceEvent:
    channel: str
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


class BenchmarkPrivacyAdapter:
    """One adapter contract used at every LLM/tool boundary.

    The three upstream repositories use different loops.  Their integration
    code only needs to call these six methods at the corresponding hook points.
    """

    SUPPORTED_METHODS = frozenset(
        {"vanilla", "deletion", "llm-rewrite", "fixed-alias", "finscope"}
    )

    def __init__(self, agent: LocalPrivacyAgent, config: PrivacyRunConfig) -> None:
        if config.method not in self.SUPPORTED_METHODS:
            raise ValueError("unsupported method %r" % config.method)
        self.agent = agent
        self.config = config
        self._scopes: Dict[str, Scope] = {}
        self._traces: Dict[str, list] = {}

    def open_episode(self, context: EpisodeContext) -> Scope:
        task_id = "%s:%s" % (context.benchmark.value, context.episode_id)
        scope = self.agent.open_scope(
            task_id,
            context.trading_day,
            conversation_id=context.conversation_id,
        )
        self._scopes[context.episode_id] = scope
        self._traces.setdefault(context.episode_id, [])
        return scope

    def sanitize_llm_input(self, value: Any, episode_id: str) -> Any:
        scope = self._scope(episode_id)
        result = self._apply_method(value, scope)
        self._trace(episode_id, "llm_input", result)
        return result

    def sanitize_tool_result(self, value: Any, episode_id: str) -> Any:
        scope = self._scope(episode_id)
        result = self._apply_method(value, scope)
        self._trace(episode_id, "tool_response", result)
        return result

    def restore_llm_output(
        self, value: Any, episode_id: str, *, execution: bool = False
    ) -> RestorationResult:
        scope = self._scope(episode_id)
        if self.config.method == "vanilla":
            result = RestorationResult(value, "safe")
        else:
            result = self.agent.restore_and_audit(value, scope, execution=execution)
        self._trace(episode_id, "llm_output", value, status=result.status)
        return result

    def validate_action(
        self, action: Mapping[str, Any], episode_id: str
    ) -> ValidationResult:
        scope = self._scope(episode_id)
        result = self.agent.validate_action(action, scope)
        self._trace(episode_id, "final_action", result.action, valid=result.valid)
        return result

    def close_episode(self, episode_id: str) -> Tuple[TraceEvent, ...]:
        scope = self._scope(episode_id)
        trace = tuple(self._traces.pop(episode_id, ()))
        self.agent.close_scope(scope)
        self._scopes.pop(episode_id, None)
        return trace

    def _apply_method(self, value: Any, scope: Scope) -> Any:
        if self.config.method == "vanilla":
            return value
        if self.config.method == "finscope":
            return self.agent.sanitize(
                value,
                scope,
                disclosure_level=self.config.disclosure_level,
                purpose=self.config.purpose,
                recipient=self.config.recipient,
                adaptive=self.config.adaptive,
            )
        # Baseline transforms intentionally reuse the same locally detected
        # entity set so comparisons do not gain an unfair recognizer advantage.
        anonymous = self.agent.mediator.sanitize(value, scope)
        if self.config.method == "fixed-alias":
            return anonymous
        if self.config.method == "deletion":
            return self.agent._replace_value(
                anonymous,
                {
                    row["alias"].upper(): "[已删除]"
                    for row in self.agent.mediator.get_mapping_records(scope)
                },
            )
        if self.config.method == "llm-rewrite":
            # Rewriting is performed by the experiment runner's configured LLM.
            # This marker makes accidental use without that call observable.
            return {"rewrite_required": True, "anonymous_input": anonymous}
        raise AssertionError("unreachable")

    def _scope(self, episode_id: str) -> Scope:
        try:
            return self._scopes[episode_id]
        except KeyError as exc:
            raise KeyError("episode %r is not open" % episode_id) from exc

    def _trace(self, episode_id: str, channel: str, value: Any, **metadata: Any) -> None:
        self._traces[episode_id].append(TraceEvent(channel, value, dict(metadata)))
