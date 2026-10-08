from typing import Protocol

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import EMBEDDING_DIM, EmbeddingIndex, IndexStatus

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    model_name: str
    dimensions: int
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class LocalEmbedder:
    """Development only: runs inside the container, no data leaves the machine."""

    def __init__(self, model_name: str, cache_dir: str):
        from fastembed import TextEmbedding
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dimensions = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([BGE_QUERY_PREFIX + text]))).tolist()


def get_embedder() -> Embedder:
    if settings.embedding_provider == "local":
        return LocalEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")


def ensure_active_index(db, embedder: Embedder) -> int:
    if embedder.dimensions != EMBEDDING_DIM:
        raise RuntimeError(
            f"{embedder.model_name} produces {embedder.dimensions} dimensions, but the schema "
            f"stores {EMBEDDING_DIM}. A migration and full re-embedding are required.")
    active = db.scalar(select(EmbeddingIndex).where(EmbeddingIndex.status == IndexStatus.active))
    if active is None:
        active = EmbeddingIndex(model_name=embedder.model_name, dimensions=embedder.dimensions,
                                status=IndexStatus.active, activated_at=func.now())
        db.add(active)
        db.commit()
        return active.id
    if active.model_name != embedder.model_name or active.dimensions != embedder.dimensions:
        raise RuntimeError(
            f"Configured model {embedder.model_name} does not match the active index "
            f"{active.model_name} ({active.dimensions} dims). Run a controlled re-embedding "
            f"instead of mixing vectors.")
    return active.id