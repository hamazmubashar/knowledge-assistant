from sqlalchemy import func, select

from app.core.authz import allowed_groups
from app.db.models import Chunk, Document, DocumentVersion, Embedding, VersionStatus

RRF_K = 60


def _visible(stmt, groups):
    return (stmt
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.status == VersionStatus.published,
                   Document.is_deleted.is_(False),
                   Chunk.access_group.in_(groups)))


def search(db, user, query, embedder, index_id, k=5, candidates=20):
    groups = list(allowed_groups(db, user))
    if not groups:
        return []

    qvec = embedder.embed_query(query)
    distance = Embedding.embedding.cosine_distance(qvec)
    vector_ids = db.scalars(
        _visible(select(Chunk.id).select_from(Chunk)
                 .join(Embedding, Embedding.chunk_id == Chunk.id), groups)
        .where(Embedding.index_id == index_id)
        .order_by(distance).limit(candidates)
    ).all()

    tsq = func.websearch_to_tsquery("english", query)
    keyword_ids = db.scalars(
        _visible(select(Chunk.id).select_from(Chunk), groups)
        .where(Chunk.search_vector.op("@@")(tsq))
        .order_by(func.ts_rank_cd(Chunk.search_vector, tsq).desc())
        .limit(candidates)
    ).all()

    scores, vrank, krank = {}, {}, {}
    for rank, cid in enumerate(vector_ids, start=1):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
        vrank[cid] = rank
    for rank, cid in enumerate(keyword_ids, start=1):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
        krank[cid] = rank
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    if not top:
        return []

    rows = db.execute(
        _visible(select(Chunk, DocumentVersion.version_number, Document.title)
                 .select_from(Chunk), groups)
        .where(Chunk.id.in_(top))
    ).all()
    by_id = {row[0].id: row for row in rows}

    results = []
    for cid in top:
        if cid not in by_id:
            continue
        chunk, version_number, title = by_id[cid]
        results.append({
            "chunk_id": str(chunk.id),
            "document_id": str(chunk_document_id(db, chunk)),
            "document_title": title,
            "version_id": str(chunk.version_id),
            "version_number": version_number,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "heading": chunk.heading,
            "text": chunk.text,
            "access_group": chunk.access_group.value,
            "extraction_method": chunk.extraction_method.value,
            "low_confidence": chunk.low_confidence,
            "score": round(scores[cid], 5),
            "vector_rank": vrank.get(cid),
            "keyword_rank": krank.get(cid),
        })
    return results


def chunk_document_id(db, chunk):
    return db.scalar(select(DocumentVersion.document_id)
                     .where(DocumentVersion.id == chunk.version_id))