import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.authz import can_manage, ensure_can_view
from app.core.config import settings
from app.db.models import AccessGroup, AuditLog, Document, DocumentVersion, User
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
    user: User = Depends(get_current_user),
):
    if not can_manage(db, user, access_group):
        raise HTTPException(status_code=403, detail="Not allowed to manage this group")

    data = file.file.read()
    try:
        validate_pdf(file.filename or "", data, settings.max_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc = Document(title=title, access_group=access_group, created_by=user.id)
    db.add(doc)
    db.flush()
    version = DocumentVersion(
        document_id=doc.id, version_number=1, original_filename=file.filename,
        file_hash=hashlib.sha256(data).hexdigest(), uploaded_by=user.id,
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
                    details={"size_bytes": len(data)}))
    db.commit()
    return {"document_id": str(doc.id), "version_id": str(version.id), "status": "queued"}


def _get_viewable_version(db, user, version_id) -> DocumentVersion:
    v = db.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Not found")
    ensure_can_view(db, user, db.get(Document, v.document_id))
    return v


@router.get("/versions/{version_id}")
def get_version(version_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    v = _get_viewable_version(db, user, version_id)
    return {
        "version_id": str(v.id), "document_id": str(v.document_id),
        "status": v.status.value, "page_count": v.page_count, "attempts": v.attempts,
        "error_step": v.error_step, "error_message": v.error_message,
    }


@router.get("/versions/{version_id}/file")
def download_version(version_id: uuid.UUID, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    v = _get_viewable_version(db, user, version_id)
    if not v.storage_key:
        raise HTTPException(status_code=404, detail="Not found")
    data = storage.get_pdf(v.storage_key)
    db.add(AuditLog(actor_id=user.id, action="document.download",
                    target_type="document_version", target_id=str(v.id)))
    db.commit()
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="document.pdf"'})