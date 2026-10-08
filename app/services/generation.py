import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


@dataclass
class GenerationResult:
    text: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None


class Generator(Protocol):
    model_name: str
    def generate(self, system: str, user: str, schema: dict | None = None) -> GenerationResult: ...


class OllamaGenerator:
    """Local development and evaluation only. Synthetic documents only."""

    def __init__(self, model_name: str, base_url: str, timeout: int):
        self.model_name = model_name
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def generate(self, system: str, user: str, schema: dict | None = None) -> GenerationResult:
        start = time.perf_counter()
        r = self._client.post("/api/chat", json={
            "model": self.model_name,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": schema or "json",
            "options": {"temperature": 0, "num_ctx": 8192},
        })
        r.raise_for_status()
        body = r.json()
        return GenerationResult(
            text=body["message"]["content"],
            model=self.model_name,
            latency_ms=round((time.perf_counter() - start) * 1000),
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
        )


def get_generator(model_name: str | None = None) -> Generator:
    if settings.generation_provider == "ollama":
        return OllamaGenerator(model_name or settings.generation_model,
                               settings.ollama_base_url, settings.generation_timeout_seconds)
    raise ValueError(f"Unknown generation provider: {settings.generation_provider}")