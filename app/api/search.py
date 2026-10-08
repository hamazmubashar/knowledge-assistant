from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.services.retrieval import search

router = APIRouter()


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


@router.post("/search")
def search_endpoint(body: SearchIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    results = search(db, user, body.query.strip(), request.app.state.embedder,
                     request.app.state.index_id, k=body.k)
    db.add(AuditLog(actor_id=user.id, action="search", details={"results": len(results)}))
    db.commit()
    return {"results": results}