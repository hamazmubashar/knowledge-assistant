import hashlib

import pymupdf
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (AccessGroup, Document, DocumentVersion, Role, User,
                           VersionStatus)
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


def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing to seed: DATABASE_URL must point to the knowledge_eval database.")
    storage.ensure_bucket()

    with SessionLocal() as db:
        admin = User(email="eval-admin@local.test", password_hash="!disabled", role=Role.hr)
        db.add(admin)
        db.flush()
        for d in DOCS:
            data = build_pdf(d["pages"], d["scanned"])
            doc = Document(title=d["title"], access_group=AccessGroup(d["group"]),
                           created_by=admin.id)
            db.add(doc)
            db.flush()
            v = DocumentVersion(document_id=doc.id, version_number=1,
                                original_filename="eval.pdf",
                                file_hash=hashlib.sha256(data).hexdigest(),
                                uploaded_by=admin.id)
            db.add(v)
            db.flush()
            v.storage_key = f"documents/{doc.id}/{v.id}.pdf"
            storage.put_pdf(v.storage_key, data)
        db.commit()

    embedder = get_embedder()
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
    while True:
        with SessionLocal() as db:
            claimed = claim_next(db)
        if not claimed:
            break
        process(*claimed, embedder, index_id)

    with SessionLocal() as db:
        rows = db.execute(select(Document.title, DocumentVersion.status)
                          .join(DocumentVersion, DocumentVersion.document_id == Document.id)).all()
    not_published = [t for t, s in rows if s != VersionStatus.published]
    print(f"Seeded {len(rows)} documents; not published: {not_published or 'none'}")
    if not_published:
        raise SystemExit(1)


if __name__ == "__main__":
    main()