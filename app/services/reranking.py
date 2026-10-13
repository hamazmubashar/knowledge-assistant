"""Local cross-encoder reranker: reads the question and each passage together.

Runs inside our container (fastembed, ONNX on CPU); no document text leaves the machine.
Off by default (settings.reranker_enabled), so behaviour only changes when switched on.
"""
from functools import lru_cache

from app.core.config import settings


class LocalReranker:
    def __init__(self, model_name: str, cache_dir: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self.model_name = model_name
        self._model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        return [float(s) for s in self._model.rerank(query, passages)]


@lru_cache(maxsize=1)
def get_reranker():
    if not settings.reranker_enabled:
        return None
    return LocalReranker(settings.reranker_model, settings.embedding_cache_dir)


def passage_text(result: dict) -> str:
    """Same fields the embeddings see: title, heading, text."""
    parts = [result.get("document_title") or "", result.get("heading") or "", result.get("text") or ""]
    return "\n".join(p for p in parts if p)


def rerank(query: str, results: list[dict], reranker, k: int) -> list[dict]:
    """Score every candidate, attach rerank_score, return the best k (highest score first).

    Candidates are already filtered by access rights, so reranking cannot surface restricted text.
    """
    if reranker is None or not results:
        return results[:k]
    scores = reranker.score(query, [passage_text(r) for r in results])
    scored = [{**r, "rerank_score": round(s, 4)} for r, s in zip(results, scores)]
    return sorted(scored, key=lambda r: r["rerank_score"], reverse=True)[:k]
