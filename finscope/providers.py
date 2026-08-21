"""Secret-safe OpenAI-compatible model clients used by FinScope experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Dict, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    base_url: str
    api_key: str = field(default="", repr=False)
    extra_headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    temperature: float = 0.0

    def redacted(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "header_names": sorted(self.extra_headers),
            "temperature": self.temperature,
        }


class OpenAICompatibleChatModel:
    """Small wrapper that never logs credentials and imports ``openai`` lazily."""

    def __init__(self, profile: ModelProfile, *, client: Optional[Any] = None) -> None:
        self.profile = profile
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "install the provider extra: pip install -e '.[providers]'"
                ) from exc
            client = OpenAI(
                base_url=profile.base_url,
                api_key=profile.api_key or "EMPTY",
            )
        self._client = client

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.profile.model,
            "messages": [dict(message) for message in messages],
            "temperature": (
                self.profile.temperature if temperature is None else temperature
            ),
            "stream": False,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if self.profile.extra_headers:
            kwargs["extra_headers"] = dict(self.profile.extra_headers)
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def __call__(self, prompt: str) -> str:
        return self.chat(
            (
                {
                    "role": "system",
                    "content": "Return only the structured result requested by the user.",
                },
                {"role": "user", "content": prompt},
            )
        )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError("required environment variable %s is not set" % name)
    return value


def local_qwen_profile() -> ModelProfile:
    """Profile for a local vLLM/SGLang server hosting Qwen3.8-27B."""

    return ModelProfile(
        name="local-qwen3.8-27b",
        model=os.environ.get("FINSCOPE_QWEN_MODEL", "Qwen/Qwen3.8-27B"),
        base_url=os.environ.get("FINSCOPE_QWEN_BASE_URL", "http://127.0.0.1:8000/v1"),
        api_key=os.environ.get("FINSCOPE_QWEN_API_KEY", "EMPTY"),
        temperature=float(os.environ.get("FINSCOPE_QWEN_TEMPERATURE", "0")),
    )


def enterprise_profile(model_kind: str) -> ModelProfile:
    """Build a DeepSeek or GLM profile for the enterprise gateway.

    Private gateways commonly expose aliases that differ from official model
    IDs, so the model value is intentionally required from the environment.
    """

    kind = model_kind.strip().casefold()
    if kind not in {"deepseek", "glm"}:
        raise ValueError("model_kind must be 'deepseek' or 'glm'")
    model_env = "EFUNDS_DEEPSEEK_MODEL" if kind == "deepseek" else "EFUNDS_GLM_MODEL"
    headers = {}
    for header, env_name in (
        ("Efunds-User-Name", "EFUNDS_USER_NAME"),
        ("Efunds-Acc-Token", "EFUNDS_ACC_TOKEN"),
        ("Efunds-Source", "EFUNDS_SOURCE"),
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            headers[header] = value
    return ModelProfile(
        name="enterprise-%s" % kind,
        model=_required_env(model_env),
        base_url=os.environ.get("EFUNDS_BASE_URL", "https://aigc.efunds.com.cn/v1"),
        api_key=_required_env("EFUNDS_API_KEY"),
        extra_headers=headers,
        temperature=float(os.environ.get("EFUNDS_TEMPERATURE", "0")),
    )


def experiment_profiles() -> Dict[str, ModelProfile]:
    """Load the three model profiles used by the planned experiment matrix."""

    return {
        "qwen": local_qwen_profile(),
        "deepseek": enterprise_profile("deepseek"),
        "glm": enterprise_profile("glm"),
    }
