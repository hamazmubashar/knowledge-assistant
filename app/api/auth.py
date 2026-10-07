from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import AuditLog, User
from app.db.session import get_db

router = APIRouter()
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not user.is_active or not valid:
        db.add(AuditLog(actor_id=user.id if user else None, action="auth.login_failed"))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    db.add(AuditLog(actor_id=user.id, action="auth.login"))
    db.commit()
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer"}