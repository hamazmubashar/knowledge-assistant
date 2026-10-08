from app.services.answering import numbers_supported, support_check
from app.services.generation import GenerationResult


class FakeGenerator:
    model_name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def generate(self, system, user, schema=None):
        self.calls += 1
        return GenerationResult(text=self.reply, model="fake", latency_ms=1,
                                input_tokens=1, output_tokens=1)


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