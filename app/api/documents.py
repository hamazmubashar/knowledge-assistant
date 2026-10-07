import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dev_user import get_dev_user
from app.db.models import AccessGroup, AuditLog, Document, DocumentVersion
from app.db.session import get_db
from app.services import storage
from app.services.validation import validate_pdf

router = APIRouter()


@router.post("/documents", status_code=201)
def upload_document(
    title: str = Form(...),
    access_group: AccessGroup = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = file.file.read()
    try:
        validate_pdf(file.filename or "", data, settings.max_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = get_dev_user(db)  # TODO Day 4: authenticated user + admin scope check

    doc = Document(title=title, access_group=access_group, created_by=user.id)
    db.add(doc)
    db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        original_filename=file.filename,
        file_hash=hashlib.sha256(data).hexdigest(),
        uploaded_by=user.id,
    )
    db.add(version)
    db.flush()

    key = f"documents/{doc.id}/{version.id}.pdf"
    try:
        storage.put_pdf(key, data)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="Storage unavailable, try again")

    version.storage_key = key
    db.add(AuditLog(actor_id=user.id, action="document.upload",
                    target_type="document_version", target_id=str(version.id),
                    details={"filename": file.filename, "size_bytes": len(data)}))
    db.commit()
    return {"document_id": str(doc.id), "version_id": str(version.id), "status": "queued"}


@router.get("/versions/{version_id}")
def get_version(version_id: uuid.UUID, db: Session = Depends(get_db)):
    v = db.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "version_id": str(v.id),
        "document_id": str(v.document_id),
        "status": v.status.value,
        "page_count": v.page_count,
        "attempts": v.attempts,
        "error_step": v.error_step,
        "error_message": v.error_message,
    }