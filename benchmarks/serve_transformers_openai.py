"""Serve a local Transformers chat model through a minimal OpenAI API."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import threading
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional


class TransformersChatService:
    """Single-GPU, serialized chat-completion service."""

    def __init__(
        self,
        model_path: str,
        device: str,
        served_model_name: str,
        max_output_tokens: int,
        format_guard: bool,
        do_sample: bool,
    ) -> None:
        import torch
        import transformers
        from transformers import (
            AutoConfig,
            AutoModelForCausalLM,
            AutoModelForImageTextToText,
            AutoProcessor,
            AutoTokenizer,
        )

        self.torch = torch
        self.transformers_version = transformers.__version__
        self.device = device
        self.served_model_name = served_model_name
        self.max_output_tokens = max_output_tokens
        self.format_guard = format_guard
        self.do_sample = do_sample
        self.lock = threading.Lock()
        config = AutoConfig.from_pretrained(model_path, local_files_only=True)
        architectures = tuple(config.architectures or ())
        text_only = any(name.endswith("ForCausalLM") for name in architectures)
        if text_only:
            self.processor = AutoTokenizer.from_pretrained(
                model_path, local_files_only=True
            )
            model_class = AutoModelForCausalLM
        else:
            self.processor = AutoProcessor.from_pretrained(
                model_path, local_files_only=True
            )
            model_class = AutoModelForImageTextToText
        self.tokenizer = getattr(self.processor, "tokenizer", self.processor)
        self.model = model_class.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map=device,
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    @staticmethod
    def normalize_messages(
        messages: Any,
        format_guard: bool = False,
    ) -> List[Dict[str, str]]:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")
        normalized = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise ValueError("each message must be an object")
            role = str(message.get("role", "user"))
            content = message.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, Mapping) and part.get("type") == "text":
                        text_parts.append(str(part.get("text", "")))
                content = "\n".join(text_parts)
            normalized.append({"role": role, "content": str(content)})
        if format_guard:
            for message in reversed(normalized):
                if message["role"] == "user":
                    message["content"] += (
                        "\n\n[OUTPUT PROTOCOL]\n"
                        "Return only the final structured answer requested by the user. "
                        "Do not emit analysis, reasoning, <think> blocks, markdown, or commentary. "
                        "If the request specifies an XML-like tag, include that tag and only its "
                        "strictly valid JSON payload. Cover every required item. Be concise: use "
                        "one or two short data-grounded reasons per item and do not repeat boilerplate."
                    )
                    break
        return normalized

    def generate(
        self,
        messages: Any,
        requested_tokens: Optional[int],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized = self.normalize_messages(messages, self.format_guard)
        formatted = self.processor.apply_chat_template(
            normalized,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = self.processor(text=formatted, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        output_limit = min(
            max(1, int(requested_tokens or self.max_output_tokens)),
            self.max_output_tokens,
        )
        started = time.perf_counter()
        with self.lock, self.torch.inference_mode():
            generation_kwargs = {
                "max_new_tokens": output_limit,
                "do_sample": bool(self.do_sample and temperature and temperature > 0),
                "pad_token_id": self.tokenizer.eos_token_id,
            }
            if generation_kwargs["do_sample"]:
                generation_kwargs["temperature"] = float(temperature)
                if top_p is not None:
                    generation_kwargs["top_p"] = float(top_p)
                if top_k is not None:
                    generation_kwargs["top_k"] = int(top_k)
            if seed is not None:
                self.torch.manual_seed(int(seed))
            generated = self.model.generate(
                **inputs,
                **generation_kwargs,
            )
        completion_ids = generated[0][prompt_tokens:]
        content = self.tokenizer.decode(completion_ids, skip_special_tokens=True).strip()
        completion_tokens = int(completion_ids.shape[-1])
        return {
            "id": "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "model": self.served_model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": (
                        "length" if completion_tokens >= output_limit else "stop"
                    ),
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "system_fingerprint": (
                f"transformers-{self.transformers_version}-{time.perf_counter() - started:.3f}s"
            ),
        }


def create_app(args: argparse.Namespace):
    from fastapi import FastAPI, HTTPException

    state: Dict[str, TransformersChatService] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        state["service"] = TransformersChatService(
            args.model,
            args.device,
            args.served_model_name,
            args.max_output_tokens,
            args.format_guard,
            args.do_sample,
        )
        yield
        state.clear()

    app = FastAPI(title="FinScope local Transformers OpenAI server", lifespan=lifespan)

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "model": args.served_model_name}

    @app.get("/v1/models")
    def models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": args.served_model_name,
                    "object": "model",
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    def completions(body: Dict[str, Any]) -> Dict[str, Any]:
        if body.get("stream"):
            raise HTTPException(status_code=400, detail="streaming is not supported")
        try:
            return state["service"].generate(
                body.get("messages"),
                body.get("max_tokens", body.get("max_completion_tokens")),
                body.get("temperature"),
                body.get("top_p"),
                body.get("top_k"),
                body.get("seed"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--served-model-name", default="Qwen3.8-27B")
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument(
        "--format-guard",
        action="store_true",
        help="append a strict no-analysis/JSON-only instruction to the final user message",
    )
    parser.add_argument(
        "--do-sample",
        action="store_true",
        help="honor request sampling parameters when temperature is positive",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    return parser.parse_args()


def main() -> None:
    import uvicorn

    args = parse_args()
    uvicorn.run(create_app(args), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
