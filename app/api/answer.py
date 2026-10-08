from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.services.answering import answer

router = APIRouter()


class AnswerIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/answer")
def answer_endpoint(body: AnswerIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    s = request.app.state
    result = answer(db, user, body.question.strip(), s.embedder, s.index_id, s.generator)
    db.add(AuditLog(actor_id=user.id, action="answer", details={
        "status": result["status"], "reason": result["refusal_reason"],
        "sentences": len(result["sentences"])}))
    db.commit()
    return result