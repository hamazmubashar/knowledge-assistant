from app.services import answering
from app.services.answering import evidence_sufficient
from app.services.reranking import passage_text, rerank


class FakeReranker:
    """Scores a passage by how many question words it contains."""
    def score(self, query, passages):
        words = set(query.lower().split())
        return [float(len(words & set(p.lower().split()))) for p in passages]


def result(cid, text, title="Doc"):
    return {"chunk_id": cid, "document_title": title, "heading": None, "text": text, "distance": 0.2}


def test_rerank_orders_by_score_and_keeps_k():
    results = [result("a", "nothing relevant"), result("b", "forklift speed limit 8 km/h"),
               result("c", "forklift training")]
    out = rerank("what is the forklift speed limit", results, FakeReranker(), k=2)
    assert [r["chunk_id"] for r in out] == ["b", "c"]
    assert out[0]["rerank_score"] > out[1]["rerank_score"]


def test_rerank_off_keeps_original_order():
    results = [result("a", "x"), result("b", "y"), result("c", "z")]
    assert [r["chunk_id"] for r in rerank("q", results, None, k=2)] == ["a", "b"]


def test_rerank_never_adds_passages_that_were_not_retrieved():
    # Access control happens before reranking: the reranker only reorders what the user may see.
    results = [result("a", "visible text")]
    assert [r["chunk_id"] for r in rerank("visible", results, FakeReranker(), k=5)] == ["a"]


def test_passage_text_matches_embedding_fields():
    r = {"document_title": "T", "heading": "H", "text": "body"}
    assert passage_text(r) == "T\nH\nbody"


def test_gate_uses_rerank_score_when_enabled(monkeypatch):
    monkeypatch.setattr(answering.settings, "rerank_min_score", 0.0)
    monkeypatch.setattr(answering.settings, "answer_max_distance", 0.30)
    assert evidence_sufficient(0.33, 2.5, reranker_enabled=True)       # far by distance, relevant by reranker
    assert not evidence_sufficient(0.10, -3.0, reranker_enabled=True)  # close by distance, irrelevant by reranker
    assert not evidence_sufficient(None, 5.0, reranker_enabled=True)   # nothing visible matched
    assert evidence_sufficient(0.25, None, reranker_enabled=False)     # off: distance decides as before
    assert not evidence_sufficient(0.33, None, reranker_enabled=False)
