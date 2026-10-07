import logging
import os
import tempfile
import time

import pymupdf
from sqlalchemy import select

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
    v.error_step = None
    v.error_message = None
    db.commit()
    return v.id


def process(version_id):
    step = "download"
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    with SessionLocal() as db:
        try:
            v = db.get(DocumentVersion, version_id)
            storage.download_to(v.storage_key, tmp.name)
            step = "extract"
            with pymupdf.open(tmp.name) as pdf:
                for i, page in enumerate(pdf, start=1):
                    db.add(Page(version_id=v.id, page_number=i,
                                text=page.get_text("text"),
                                extraction_method=ExtractionMethod.pymupdf))
                v.page_count = pdf.page_count
            v.status = VersionStatus.ready
            db.commit()
            log.info("version %s ready, %s pages", version_id, v.page_count)
        except Exception as e:
            db.rollback()
            v = db.get(DocumentVersion, version_id)
            v.status = VersionStatus.failed
            v.error_step = step
            v.error_message = type(e).__name__
            db.commit()
            log.error("version %s failed at %s: %s", version_id, step, type(e).__name__)
        finally:
            os.remove(tmp.name)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("worker started")
    while True:
        with SessionLocal() as db:
            version_id = claim_next(db)
        if version_id:
            process(version_id)
        else:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()