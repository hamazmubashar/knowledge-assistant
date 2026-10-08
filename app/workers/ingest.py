import logging
import os
import tempfile
import time
from datetime import timedelta

import pymupdf
from sqlalchemy import delete, func, or_, select, update

from app.core.config import settings
from app.db.models import DocumentVersion, ExtractionMethod, Page, VersionStatus
from app.db.session import SessionLocal
from app.services import storage

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
        with pymupdf.open(tmp.name) as pdf:
            pages = [(n, p.get_text("text")) for n, p in enumerate(pdf, start=1)]

        step = "save"
        with SessionLocal() as db:
            v = owned_version(db, version_id, attempt)
            if v is None:
                db.rollback()
                log.warning("version %s attempt %s is stale; results discarded", version_id, attempt)
                return
            db.execute(delete(Page).where(Page.version_id == version_id))
            db.add_all([Page(version_id=version_id, page_number=n, text=t,
                             extraction_method=ExtractionMethod.pymupdf) for n, t in pages])
            v.page_count = len(pages)
            v.status = VersionStatus.ready
            db.commit()
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