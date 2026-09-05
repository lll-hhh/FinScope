"""Build the model-assisted local FinScope agent used in final experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from finscope import (
    FinScopeMediator,
    JsonModelDisclosurePlanner,
    JsonModelEntityRecognizer,
    JsonModelRecoveryAuditor,
    LocalPrivacyAgent,
    ModelProfile,
    OpenAICompatibleChatModel,
)


@dataclass(frozen=True)
class LocalPrivacyModelConfig:
    name: str
    base_url: str
    model: str
    default_level: str = "P3"


@dataclass
class LocalPrivacyAgentBundle:
    agent: LocalPrivacyAgent
    model: OpenAICompatibleChatModel
    config: LocalPrivacyModelConfig

    def usage(self) -> Dict[str, float]:
        return self.model.metrics()

    def metadata(self) -> Dict[str, Any]:
        return {
            "name": self.config.name,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "roles": ["residual_entity_recognition", "disclosure_planning", "recovery_audit"],
            # A local model failure is handled by the security-master-derived
            # fail-safe plan. The model still proposes every plan; fallback
            # events are counted and reported rather than hidden.
            "planner_fallback_allowed": True,
        }


def build_model_assisted_agent(
    catalog: Sequence[Mapping[str, Any]],
    config: LocalPrivacyModelConfig,
) -> LocalPrivacyAgentBundle:
    """Use one local small model for three constrained, code-validated roles."""

    model = OpenAICompatibleChatModel(
        ModelProfile(
            name=config.name,
            model=config.model,
            base_url=config.base_url,
            api_key="local",
            temperature=0.0,
        )
    )
    def structured_call(prompt: str) -> str:
        # Keep the local model inside a bounded JSON budget. The planner,
        # recognizer and auditor are all schema-constrained; long generations
        # increase truncation and malformed-output probability without adding
        # useful evidence.
            return model.chat(
            (
                {
                    "role": "system",
                    "content": "Return only the requested JSON object.",
                },
                {"role": "user", "content": prompt},
            ),
            max_tokens=512,
        )

    recognizer = JsonModelEntityRecognizer(structured_call)
    mediator = FinScopeMediator(catalog, entity_recognizer=recognizer)
    agent = LocalPrivacyAgent(
        catalog,
        mediator=mediator,
        disclosure_planner=JsonModelDisclosurePlanner(
            structured_call, allow_fallback=True
        ),
        recovery_auditor=JsonModelRecoveryAuditor(structured_call),
        default_level=config.default_level,
    )
    return LocalPrivacyAgentBundle(agent=agent, model=model, config=config)


def usage_delta(
    before: Mapping[str, float], after: Mapping[str, float]
) -> Dict[str, float]:
    return {key: float(after.get(key, 0.0)) - float(before.get(key, 0.0)) for key in after}
