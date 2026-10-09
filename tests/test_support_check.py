from app.services.answering import (ensure_independent_judge, numbers_supported,
                                    relevance_check, support_check)
from app.services.generation import CachedGenerator, GenerationResult


class FakeGenerator:
    provider = "fake"
    model_name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def generate(self, system, user, schema=None):
        self.calls += 1
        return GenerationResult(text=self.reply, model="fake", latency_ms=1,
                                input_tokens=1, output_tokens=1)

def test_no_judge_fails_closed_on_reworded_sentence():
    kept, dropped, _ = support_check([S], None)
    assert kept == [] and dropped == ["unverified_no_judge"]


def test_irrelevant_sentence_is_dropped():
    kept, dropped, _ = relevance_check("q", [S], FakeGenerator('{"relevant": false}'))
    assert kept == [] and dropped == ["not_relevant"]


def test_relevance_unreadable_reply_fails_closed():
    kept, dropped, _ = relevance_check("q", [S], FakeGenerator("not json"))
    assert kept == [] and dropped == ["not_relevant"]


def test_relevant_sentence_is_kept():
    kept, _, _ = relevance_check("q", [S], FakeGenerator('{"relevant": true}'))
    assert kept == [S]


def test_judge_cannot_be_the_answer_model():
    import pytest
    same = FakeGenerator("x")
    with pytest.raises(ValueError):
        ensure_independent_judge(same, FakeGenerator("y"))


def test_different_judge_is_allowed():
    other = FakeGenerator("x")
    other.model_name = "other-model"
    ensure_independent_judge(FakeGenerator("x"), other)


def test_cache_replays_without_calling_model(tmp_path):
    inner = FakeGenerator('{"supported": true}')
    cached = CachedGenerator(inner, tmp_path)
    first = cached.generate("s", "u")
    second = cached.generate("s", "u")
    assert inner.calls == 1 and not first.cached and second.cached

S = {"text": "Full-time staff get 20 days of leave.", "evidence_id": "SOURCE_1",
     "quote": "Full-time staff receive 20 days of paid annual leave", "reattributed": False}


def test_wrong_number_is_caught_without_a_model_call():
    gen = FakeGenerator('{"supported": true}')
    bad = {**S, "text": "Full-time staff get 30 days of leave."}
    kept, dropped, _ = support_check([bad], gen)
    assert kept == [] and dropped == ["number_mismatch"] and gen.calls == 0


def test_numbers_must_all_appear_in_quote():
    assert numbers_supported("Band C is 4,000 to 5,500", "C | 4,000 - 5,500 | April")
    assert not numbers_supported("Band C is 4,000 to 6,000", "C | 4,000 - 5,500 | April")
    assert numbers_supported("E04 means no internet", "E04 | No internet connection")


def test_model_rejection_removes_sentence():
    kept, dropped, _ = support_check([S], FakeGenerator('{"supported": false}'))
    assert kept == [] and dropped == ["not_supported"]


def test_unreadable_reply_fails_closed():
    kept, dropped, _ = support_check([S], FakeGenerator("not json"))
    assert kept == [] and dropped == ["not_supported"]


def test_supported_sentence_is_kept():
    kept, dropped, _ = support_check([S], FakeGenerator('{"supported": true}'))
    assert kept == [S] and dropped == []

def test_verbatim_claim_is_kept_without_asking_the_model():
    gen = FakeGenerator('{"supported": false}')
    same = {**S, "text": "Full-time staff receive 20 days"}
    kept, dropped, _ = support_check([same], gen)
    assert kept == [same] and dropped == [] and gen.calls == 0

def test_real_generators_declare_their_provider():
    from app.services.generation import GeminiGenerator, OllamaGenerator
    assert OllamaGenerator.provider == "ollama"
    assert GeminiGenerator.provider == "gemini"