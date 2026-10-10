from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.authz import admin_groups, allowed_groups
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"email": user.email, "role": user.role.value,
            "admin_groups": sorted(g.value for g in admin_groups(db, user)),
            "readable_groups": sorted(g.value for g in allowed_groups(db, user))}