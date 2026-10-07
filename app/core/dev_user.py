from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import User

DEV_EMAIL = "dev-admin@local.test"


def get_dev_user(db):
    user = db.scalar(select(User).where(User.email == DEV_EMAIL))
    if user is None:
        raise HTTPException(status_code=500, detail="Dev user missing; run create_dev_user")
    return user