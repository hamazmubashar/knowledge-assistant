import time
from dataclasses import dataclass
from typing import Protocol
import hashlib
import json
from pathlib import Path
import httpx

from app.core.config import settings


@dataclass
class GenerationResult:
    text: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached: bool = False


class Generator(Protocol):
    model_name: str
    def generate(self, system: str, user: str, schema: dict | None = None) -> GenerationResult: ...


class OllamaGenerator:
    provider = "ollama"
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


class QuotaExhausted(RuntimeError):
    """Daily free-tier limit reached: stop the run, resume tomorrow."""


GEMINI_RPM = {"gemini-3.5-flash-lite": 15, "gemini-3.8-flash": 5,
              "gemma-4-31b-it": 30, "default": 5}
_last_call: dict[str, float] = {}


def _pace(model: str):
    rpm = GEMINI_RPM.get(model, GEMINI_RPM["default"])
    interval = 60 / rpm + 0.5
    wait = _last_call.get(model, 0) + interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[model] = time.monotonic()


class GeminiGenerator:
    provider = "gemini"
    """Free tier: synthetic documents only (approved by Alex)."""
    def __init__(self, model_name: str):
        from google import genai
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.model_name = model_name
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate(self, system: str, user: str, schema: dict | None = None) -> GenerationResult:
        from google.genai import errors, types
        is_gemma = self.model_name.startswith("gemma")
        config = types.GenerateContentConfig(
            system_instruction=None if is_gemma else system,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=None if is_gemma else types.ThinkingConfig(thinking_level="low"),
        )
        contents = f"{system}\n\n{user}" if is_gemma else user
        for attempt in range(3):
            _pace(self.model_name)
            start = time.perf_counter()
            try:
                resp = self._client.models.generate_content(
                    model=self.model_name, contents=contents, config=config)
                break
            except errors.ClientError as e:
                if e.code == 429 and "PerDay" in str(e):
                    raise QuotaExhausted(f"Daily limit reached for {self.model_name}")
                if e.code == 429 and attempt < 2:
                    time.sleep(20 * (attempt + 1))
                    continue
                raise
        usage = resp.usage_metadata
        output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return GenerationResult(
            text=resp.text or "",
            model=f"gemini:{self.model_name}",
            latency_ms=round((time.perf_counter() - start) * 1000),
            input_tokens=usage.prompt_token_count,
            output_tokens=output,
        )


def get_generator(model_name: str | None = None) -> Generator:
    name = model_name or settings.generation_model
    provider, _, model = name.partition(":") if name.startswith(("ollama:", "gemini:")) \
        else ("ollama", "", name)
    if provider == "gemini":
        return GeminiGenerator(model)
    return OllamaGenerator(model, settings.ollama_base_url, settings.generation_timeout_seconds)

class CachedGenerator:
    """Evaluation only: replays saved responses so reruns cost no quota."""

    def __init__(self, inner, cache_dir):
        self.inner = inner
        self.model_name = inner.model_name
        self.provider = inner.provider
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, system: str, user: str, schema: dict | None = None) -> GenerationResult:
        key = hashlib.sha256(json.dumps([self.provider, self.model_name, system, user, schema],
                                        sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return GenerationResult(**json.loads(path.read_text()), cached=True)
        r = self.inner.generate(system, user, schema)
        path.write_text(json.dumps({"text": r.text, "model": r.model, "latency_ms": r.latency_ms,
                                    "input_tokens": r.input_tokens, "output_tokens": r.output_tokens}))
        return r