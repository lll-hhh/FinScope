"""Local entity recognizers used to build FinScope mappings.

The model is deliberately constrained to span detection.  It never receives
the alias table and never creates aliases; the mediator validates its JSON and
owns all mapping and restoration state.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import threading
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class EntitySpan:
    """A span identified in the original, unsanitized text."""

    start: int
    end: int
    text: str
    entity_type: str = "asset"
    canonical: Optional[str] = None
    confidence: float = 1.0
    refers_to: Optional[str] = None
    risk: int = 2


class EntityRecognizer:
    """Small interface implemented by local or deterministic recognizers."""

    def recognize(
        self,
        text: str,
        candidate_entities: Sequence[str] = (),
    ) -> Sequence[EntitySpan]:
        raise NotImplementedError

    def clear_cache(self) -> None:
        """Optional hook used by periodic probes to force a fresh inference."""


class CatalogEntityRecognizer(EntityRecognizer):
    """Deterministic fallback for a local security master."""

    def __init__(self, entities: Sequence[str]) -> None:
        self.entities = tuple(dict.fromkeys(entity for entity in entities if entity))

    def recognize(
        self,
        text: str,
        candidate_entities: Sequence[str] = (),
    ) -> Sequence[EntitySpan]:
        entities = tuple(dict.fromkeys(self.entities + tuple(candidate_entities)))
        spans: List[EntitySpan] = []
        for entity in sorted(entities, key=len, reverse=True):
            for match in re.finditer(re.escape(entity), text, flags=re.IGNORECASE):
                if any(
                    match.start() >= span.start and match.end() <= span.end
                    for span in spans
                ):
                    continue
                spans.append(
                    EntitySpan(
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0),
                        entity_type="asset",
                    )
                )
        return sorted(spans, key=lambda span: (span.start, span.end))


class JsonModelEntityRecognizer(EntityRecognizer):
    """Constrain a local text-generation model to JSON span extraction.

    ``model_call`` receives a prompt and returns generated text.  Keeping this
    callback-based makes the recognizer usable with a local Transformers model,
    vLLM OpenAI-compatible server, or a deterministic test double.
    """

    SYSTEM_PROMPT = (
        "你是本地金融隐私实体识别器。输入中的FS_代号已经受保护，绝对不要把它返回为"
        "实体。找出其余资产、机构、组合、策略、账户、指代、动作、关系和意图。只输出"
        "合法JSON对象：{\"entities\":[{\"text\":\"原文中的精确片段\",\"type\":"
        "\"asset|institution|portfolio|strategy|account|reference|action|relation|intent\","
        "\"canonical\":null,\"refers_to\":null,\"risk\":1}]}。text必须逐字复制输入，"
        "risk必须是1到4的整数，不得推断或发明输入中不存在的文字。没有实体时输出"
        "{\"entities\":[]}。例：输入“计划减仓并转入招商银行账户”，输出"
        "{\"entities\":[{\"text\":\"减仓\",\"type\":\"action\",\"canonical\":null,"
        "\"refers_to\":null,\"risk\":3},{\"text\":\"招商银行账户\",\"type\":"
        "\"account\",\"canonical\":null,\"refers_to\":null,\"risk\":4}]}。"
    )

    def __init__(
        self,
        model_call: Callable[[str], str],
        *,
        fallback: Optional[EntityRecognizer] = None,
        max_candidates: int = 128,
        cache_size: int = 2048,
    ) -> None:
        self.model_call = model_call
        self.fallback = fallback
        self.max_candidates = max_candidates
        self.cache_size = cache_size
        self._cache: Dict[Tuple[str, Tuple[str, ...]], Tuple[EntitySpan, ...]] = {}
        self._lock = threading.RLock()
        self.calls = 0
        self.failures = 0
        self.fallbacks = 0

    def recognize(
        self,
        text: str,
        candidate_entities: Sequence[str] = (),
    ) -> Sequence[EntitySpan]:
        candidates = tuple(dict.fromkeys(candidate_entities))[: self.max_candidates]
        cache_key = (text, candidates)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        prompt = self._build_prompt(text, candidates)
        self.calls += 1
        try:
            raw = self.model_call(prompt)
            spans = self._parse_and_validate(raw, text)
        except (TypeError, ValueError, json.JSONDecodeError):
            self.failures += 1
            if self.fallback is None:
                spans = ()
            else:
                self.fallbacks += 1
                spans = tuple(self.fallback.recognize(text, candidates))

        with self._lock:
            if len(self._cache) >= self.cache_size:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = tuple(spans)
        return spans

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _build_prompt(self, text: str, candidates: Sequence[str]) -> str:
        candidate_block = "\n".join(f"- {candidate}" for candidate in candidates)
        return (
            f"SYSTEM:\n{self.SYSTEM_PROMPT}\n\n"
            f"LOCAL SECURITY-MASTER CANDIDATES:\n{candidate_block or '(none)'}\n\n"
            f"INPUT:\n{text}\n\nJSON:\n"
        )

    @classmethod
    def _parse_and_validate(cls, raw: str, source: str) -> Tuple[EntitySpan, ...]:
        if not isinstance(raw, str):
            raise TypeError("local model output must be text")
        decoder = json.JSONDecoder()
        document: Optional[Dict[str, Any]] = None
        for match in re.finditer(r"\{", raw):
            try:
                candidate, _ = decoder.raw_decode(raw[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                document = candidate
                break
        if document is None:
            raise json.JSONDecodeError("no JSON object", raw, 0)

        entities = document.get("entities", [])
        if not isinstance(entities, list):
            raise ValueError("entities must be a list")
        validated: List[EntitySpan] = []
        used_locations: List[Tuple[int, int]] = []
        for item in entities:
            if not isinstance(item, dict):
                raise ValueError("entity entries must be objects")
            start = item.get("start")
            end = item.get("end")
            reported_text = item.get("text")
            entity_type = str(item.get("type", "asset")).casefold()
            if isinstance(reported_text, str) and reported_text:
                valid_explicit_offsets = (
                    isinstance(start, int)
                    and not isinstance(start, bool)
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                    and 0 <= start < end <= len(source)
                    and source[start:end].casefold() == reported_text.casefold()
                )
                if not valid_explicit_offsets:
                    start = cls._find_unused_occurrence(
                        source,
                        reported_text,
                        used_locations,
                        item.get("occurrence"),
                    )
                if start < 0:
                    continue
                end = start + len(reported_text)
                text = source[start:end]
            else:
                # Backward-compatible support for models that emit offsets.
                if (
                    isinstance(start, bool)
                    or isinstance(end, bool)
                    or not isinstance(start, int)
                    or not isinstance(end, int)
                    or start < 0
                    or end <= start
                    or end > len(source)
                ):
                    raise ValueError("entity text or valid offsets are required")
                text = source[start:end]
            if not text.strip() or entity_type not in {
                "asset",
                "institution",
                "organization",
                "portfolio",
                "strategy",
                "account",
                "reference",
                "action",
                "relation",
                "intent",
            }:
                continue
            if re.fullmatch(r"FS_[A-Z_]+_[A-Z2-9]{8}", text, flags=re.IGNORECASE):
                continue
            canonical = item.get("canonical")
            if canonical is not None and not isinstance(canonical, str):
                canonical = None
            refers_to = item.get("refers_to")
            if refers_to is not None and not isinstance(refers_to, str):
                refers_to = None
            confidence = item.get("confidence", 1.0)
            if not isinstance(confidence, (int, float)):
                confidence = 1.0
            risk = item.get("risk", 2)
            if isinstance(risk, bool) or not isinstance(risk, (int, float)):
                risk = 2
            risk = max(1, min(4, int(risk)))
            validated.append(
                EntitySpan(
                    start=start,
                    end=end,
                    text=text,
                    entity_type=entity_type,
                    canonical=canonical,
                    confidence=float(confidence),
                    refers_to=refers_to,
                    risk=risk,
                )
            )
            used_locations.append((start, end))
        validated.sort(key=lambda span: (span.start, -(span.end - span.start)))
        non_overlapping: List[EntitySpan] = []
        for span in validated:
            if non_overlapping and span.start < non_overlapping[-1].end:
                continue
            non_overlapping.append(span)
        return tuple(non_overlapping)

    @staticmethod
    def _find_unused_occurrence(
        source: str,
        text: str,
        used_locations: Sequence[Tuple[int, int]],
        requested_occurrence: Any,
    ) -> int:
        locations = [
            (match.start(), match.end())
            for match in re.finditer(re.escape(text), source, flags=re.IGNORECASE)
        ]
        if isinstance(requested_occurrence, int) and not isinstance(
            requested_occurrence, bool
        ):
            index = requested_occurrence - 1
            if 0 <= index < len(locations):
                return locations[index][0]
        used = set(used_locations)
        for location in locations:
            if location not in used:
                return location[0]
        return -1


class TransformersEntityRecognizer(JsonModelEntityRecognizer):
    """Run a small local causal LM through ``transformers``.

    Imports are lazy so the base FinScope package remains dependency-free.  A
    suitable first model is Qwen3-0.6B with non-thinking generation enabled.
    """

    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cpu",
        max_new_tokens: int = 256,
        fallback: Optional[EntityRecognizer] = None,
        enable_thinking: bool = False,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "TransformersEntityRecognizer requires torch and transformers"
            ) from exc

        self._torch = torch
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._enable_thinking = enable_thinking
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForCausalLM.from_pretrained(model_path)
        self._model.to(device)
        self._model.eval()
        super().__init__(self._generate, fallback=fallback)

    def _generate(self, prompt: str) -> str:
        tokenizer = self._tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            messages = [{"role": "user", "content": prompt}]
            try:
                prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=self._enable_thinking,
                )
            except TypeError:
                # Qwen2.5 and other older tokenizers do not expose this flag.
                prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with self._torch.no_grad():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        input_length = inputs["input_ids"].shape[-1]
        return tokenizer.decode(generated[0][input_length:], skip_special_tokens=True)
