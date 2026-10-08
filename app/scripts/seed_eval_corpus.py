import hashlib

import pymupdf
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import AccessGroup, Document, DocumentVersion, Role, User, VersionStatus
from app.db.session import SessionLocal
from app.eval.corpus import DOCS
from app.services import storage
from app.services.embeddings import ensure_active_index, get_embedder
from app.workers.ingest import claim_next, process


def build_pdf(pages, scanned):
    out = pymupdf.open()
    for lines in pages:
        src = pymupdf.open()
        page = src.new_page()
        for i, line in enumerate(lines):
            page.insert_text((72, 72 + i * 18), line, fontsize=11)
        if scanned:
            pix = page.get_pixmap(dpi=200)
            img = out.new_page(width=page.rect.width, height=page.rect.height)
            img.insert_image(img.rect, pixmap=pix)
        else:
            out.insert_pdf(src)
        src.close()
    data = out.tobytes()
    out.close()
    return data


def add_version(db, doc_id, number, pages, scanned, admin_id):
    data = build_pdf(pages, scanned)
    v = DocumentVersion(document_id=doc_id, version_number=number, original_filename="eval.pdf",
                        file_hash=hashlib.sha256(data).hexdigest(), uploaded_by=admin_id)
    db.add(v)
    db.flush()
    v.storage_key = f"documents/{doc_id}/{v.id}.pdf"
    storage.put_pdf(v.storage_key, data)


def process_queue(embedder, index_id):
    while True:
        with SessionLocal() as db:
            claimed = claim_next(db)
        if not claimed:
            return
        process(*claimed, embedder, index_id)


def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing to seed: DATABASE_URL must point to the knowledge_eval database.")
    storage.ensure_bucket()
    embedder = get_embedder()

    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        admin = User(email="eval-admin@local.test", password_hash="!disabled", role=Role.hr)
        db.add(admin)
        db.flush()
        admin_id = admin.id
        doc_ids = {}
        for d in DOCS:
            doc = Document(title=d["title"], access_group=AccessGroup(d["group"]), created_by=admin_id)
            db.add(doc)
            db.flush()
            doc_ids[d["title"]] = doc.id
        for d in DOCS:
            if "old_pages" in d:
                add_version(db, doc_ids[d["title"]], 1, d["old_pages"], d["scanned"], admin_id)
        db.commit()
    process_queue(embedder, index_id)

    with SessionLocal() as db:
        for d in DOCS:
            number = 2 if "old_pages" in d else 1
            add_version(db, doc_ids[d["title"]], number, d["pages"], d["scanned"], admin_id)
        db.commit()
    process_queue(embedder, index_id)

    with SessionLocal() as db:
        counts = dict(db.execute(select(DocumentVersion.status, func.count())
                                 .group_by(DocumentVersion.status)).all())
    published = counts.get(VersionStatus.published, 0)
    superseded = counts.get(VersionStatus.superseded, 0)
    expected_superseded = sum(1 for d in DOCS if "old_pages" in d)
    print(f"Seeded {len(DOCS)} documents: {published} published, {superseded} superseded")
    if published != len(DOCS) or superseded != expected_superseded:
        raise SystemExit(f"Unexpected version states: {counts}")


if __name__ == "__main__":
    main()