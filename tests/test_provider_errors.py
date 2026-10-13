import httpx
import pytest

from app.services import generation
from app.services.generation import GeminiGenerator, OllamaGenerator, ProviderUnavailable


class DroppingModels:
    def __init__(self):
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")


def test_gemini_connection_drop_retries_then_stops_cleanly(monkeypatch):
    monkeypatch.setattr(generation.time, "sleep", lambda s: None)
    monkeypatch.setattr(generation, "_pace", lambda m: None)
    gen = object.__new__(GeminiGenerator)          # skip __init__: no API key needed
    gen.model_name = "gemini-3.8-flash"
    models = DroppingModels()
    gen._client = type("C", (), {"models": models})()
    with pytest.raises(ProviderUnavailable, match="connection failed after 4 attempts"):
        gen.generate("system", "user", {"type": "object"})
    assert models.calls == 4


def test_ollama_unreachable_stops_cleanly():
    def refuse(request):
        raise httpx.ConnectError("connection refused")
    gen = OllamaGenerator("qwen2.5:3b", "http://ollama.invalid", timeout=1)
    gen._client = httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://ollama.invalid")
    with pytest.raises(ProviderUnavailable, match="unreachable"):
        gen.generate("system", "user")
