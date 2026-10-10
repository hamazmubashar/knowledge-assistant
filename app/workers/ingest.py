import logging
import os
import tempfile
import time
import uuid
from datetime import timedelta

import pymupdf
from sqlalchemy import delete, func, or_, select, update
from app.services.injection import find_injection
from app.core.config import settings
from app.db.models import (Chunk, Document, DocumentVersion, Embedding, ExtractionMethod,
                           Page, VersionStatus)
from app.db.session import SessionLocal
from app.services import storage
from app.services.chunking import ContentLoss, PageInput, chunk_pages, missing_lines
from app.services.embeddings import ensure_active_index, get_embedder
from app.services.ocr import get_ocr_provider

log = logging.getLogger("ingest")
POLL_SECONDS = 3


def claim_next(db):
    v = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.status == VersionStatus.queued)
        .order_by(DocumentVersion.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if v is None:
        return None
    v.status = VersionStatus.processing
    v.attempts += 1
    v.processing_started_at = func.now()
    v.error_step = None
    v.error_message = None
    v.page_count = None
    claimed = (v.id, v.attempts)
    db.commit()
    return claimed


def owned_version(db, version_id, attempt):
    v = db.scalar(select(DocumentVersion)
                  .where(DocumentVersion.id == version_id)
                  .with_for_update())
    if v is None or v.status != VersionStatus.processing or v.attempts != attempt:
        return None
    return v


def sweep_stuck(db):
    cutoff = func.now() - timedelta(minutes=settings.stuck_timeout_minutes)
    stmt = (
        update(DocumentVersion)
        .where(DocumentVersion.status == VersionStatus.processing)
        .where(or_(DocumentVersion.processing_started_at.is_(None),
                   DocumentVersion.processing_started_at < cutoff))
        .values(status=VersionStatus.failed, error_step="timeout",
                error_message="ProcessingTimeout")
        .returning(DocumentVersion.id)
    )
    stuck_ids = db.execute(stmt).scalars().all()
    db.commit()
    for vid in stuck_ids:
        log.warning("version %s marked failed: processing timeout", vid)


def process(version_id, attempt, embedder, index_id):
    step = "download"
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        with SessionLocal() as db:
            v = db.get(DocumentVersion, version_id)
            doc = db.get(Document, v.document_id)
            storage_key, doc_id, title, group = v.storage_key, doc.id, doc.title, doc.access_group
        storage.download_to(storage_key, tmp.name)

        step = "extract"
        ocr = get_ocr_provider()
        pages = []
        with pymupdf.open(tmp.name) as pdf:
            for n, p in enumerate(pdf, start=1):
                text = p.get_text("text")
                method = ExtractionMethod.pymupdf
                if len(text.strip()) < settings.ocr_min_chars:
                    step = "ocr"
                    text = ocr.extract_text(p.get_pixmap(dpi=200).tobytes("png"))
                    method = ExtractionMethod.ocr
                    step = "extract"
                pages.append((n, text, method))

        step = "chunk"
        page_inputs = [PageInput(n, t, is_ocr=(m == ExtractionMethod.ocr)) for n, t, m in pages]
        chunks = chunk_pages(page_inputs)
        step = "chunk_completeness"
        lost = missing_lines(page_inputs, chunks)
        if lost:
            log.error("version %s: %s lines lost during chunking", version_id, len(lost))
            raise ContentLoss(f"{len(lost)} lines lost")

        step = "embed"
        vectors = embedder.embed_documents(
            [f"{title}\n{c.heading or ''}\n{c.text}" for c in chunks])

        step = "save"
        with SessionLocal() as db:
            v = owned_version(db, version_id, attempt)
            if v is None:
                db.rollback()
                log.warning("version %s attempt %s is stale; results discarded", version_id, attempt)
                return

            db.execute(delete(Chunk).where(Chunk.version_id == version_id))
            db.execute(delete(Page).where(Page.version_id == version_id))

            page_ids, page_methods = {}, {}
            for n, t, m in pages:
                pid = uuid.uuid4()
                page_ids[n], page_methods[n] = pid, m
                db.add(Page(id=pid, version_id=version_id, page_number=n, text=t,
                            extraction_method=m))
            db.flush()

            chunk_ids = []
            for c in chunks:
                cid = uuid.uuid4()
                chunk_ids.append(cid)
                db.add(Chunk(
                    id=cid, version_id=version_id, page_id=page_ids[c.page_number],
                    page_number=c.page_number, chunk_index=c.chunk_index,
                    heading=c.heading, text=c.text, token_count=c.token_estimate,
                    access_group=group, extraction_method=page_methods[c.page_number],
                    low_confidence=c.low_confidence,
                    suspected_injection=bool(find_injection(f"{c.heading or ''} {c.text}"))))
            db.flush()

            db.add_all([Embedding(chunk_id=cid, index_id=index_id, embedding=vec)
                        for cid, vec in zip(chunk_ids, vectors)])

            db.execute(update(DocumentVersion)
                       .where(DocumentVersion.document_id == doc_id,
                              DocumentVersion.status == VersionStatus.published,
                              DocumentVersion.id != version_id)
                       .values(status=VersionStatus.superseded))
            v.page_count = len(pages)
            v.status = VersionStatus.published
            v.published_at = func.now()
            db.commit()
        flagged = sum(1 for c in chunks if find_injection(f"{c.heading or ''} {c.text}"))
        log.info("version %s attempt %s published: %s pages, %s chunks, %s flagged for review",
                 version_id, attempt, len(pages), len(chunks), flagged)
    except Exception as e:
        with SessionLocal() as db:
            v = owned_version(db, version_id, attempt)
            if v is not None:
                v.status = VersionStatus.failed
                v.error_step = step
                v.error_message = type(e).__name__
                db.commit()
            else:
                db.rollback()
        log.error("version %s attempt %s failed at %s: %s", version_id, attempt, step, type(e).__name__)
    finally:
        os.remove(tmp.name)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    embedder = get_embedder()
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
    log.info("worker started; embedding index %s (%s, %s dims)",
             index_id, embedder.model_name, embedder.dimensions)
    while True:
        with SessionLocal() as db:
            sweep_stuck(db)
            claimed = claim_next(db)
        if claimed:
            process(*claimed, embedder, index_id)
        else:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()