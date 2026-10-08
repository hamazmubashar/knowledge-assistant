import sys

from sqlalchemy import select

from app.db.models import Chunk, DocumentVersion, Embedding, VersionStatus
from app.db.session import SessionLocal
from app.services.embeddings import get_embedder

question = " ".join(sys.argv[1:]) or "How many unused leave days can I carry over?"
vec = get_embedder().embed_query(question)
with SessionLocal() as db:
    rows = db.execute(
        select(Chunk.page_number, Chunk.heading,
               Embedding.embedding.cosine_distance(vec).label("distance"))
        .join(Embedding, Embedding.chunk_id == Chunk.id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .where(DocumentVersion.status == VersionStatus.published)
        .order_by("distance").limit(3)
    ).all()
print(f"Question: {question}")
for page, heading, dist in rows:
    print(f"  page {page} | {heading} | distance {dist:.3f}")