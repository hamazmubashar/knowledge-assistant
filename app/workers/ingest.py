import logging
import os
import tempfile
import time
from datetime import timedelta

import pymupdf
from sqlalchemy import delete, func, or_, select, update
from app.services.ocr import get_ocr_provider

from app.core.config import settings
from app.db.models import DocumentVersion, ExtractionMethod, Page, VersionStatus
from app.db.session import SessionLocal
from app.services import storage

import uuid

from app.db.models import Chunk, Document
from app.services.chunking import PageInput, chunk_pages

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


def process(version_id, attempt):
    step = "download"
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        with SessionLocal() as db:
            storage_key = db.get(DocumentVersion, version_id).storage_key
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
                    png = p.get_pixmap(dpi=200).tobytes("png")
                    text = ocr.extract_text(png)
                    method = ExtractionMethod.ocr
                    step = "extract"
                pages.append((n, text, method))

        step = "save"
        with SessionLocal() as db:
            v = owned_version(db, version_id, attempt)
            if v is None:
                db.rollback()
                log.warning("version %s attempt %s is stale; results discarded", version_id, attempt)
                return
            doc = db.get(Document, v.document_id)

            db.execute(delete(Chunk).where(Chunk.version_id == version_id))
            db.execute(delete(Page).where(Page.version_id == version_id))

            page_ids, page_methods = {}, {}
            for n, t, m in pages:
                pid = uuid.uuid4()
                page_ids[n], page_methods[n] = pid, m
                db.add(Page(id=pid, version_id=version_id, page_number=n, text=t,
                            extraction_method=m))
            db.flush()

            step = "chunk"
            chunks = chunk_pages([PageInput(n, t, is_ocr=(m == ExtractionMethod.ocr))
                                  for n, t, m in pages])
            db.add_all([Chunk(
                version_id=version_id, page_id=page_ids[c.page_number],
                page_number=c.page_number, chunk_index=c.chunk_index,
                heading=c.heading, text=c.text, token_count=c.token_estimate,
                access_group=doc.access_group,
                extraction_method=page_methods[c.page_number],
                low_confidence=c.low_confidence,
            ) for c in chunks])

            v.page_count = len(pages)
            v.status = VersionStatus.ready
            db.commit()
        log.info("version %s attempt %s ready, %s pages, %s chunks",
                 version_id, attempt, len(pages), len(chunks))
        log.info("version %s attempt %s ready, %s pages", version_id, attempt, len(pages))
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
        
def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("worker started")
    while True:
        with SessionLocal() as db:
            sweep_stuck(db)
            claimed = claim_next(db)
        if claimed:
            process(*claimed)
        else:
            time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()