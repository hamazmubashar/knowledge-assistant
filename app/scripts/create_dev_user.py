from sqlalchemy import select

from app.core.dev_user import DEV_EMAIL
from app.db.models import AccessGroup, AdminScope, Role, User
from app.db.session import SessionLocal


def main():
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == DEV_EMAIL)):
            print("Dev user already exists")
            return
        user = User(email=DEV_EMAIL, password_hash="!disabled", role=Role.operations)
        db.add(user)
        db.flush()
        for group in AccessGroup:
            db.add(AdminScope(user_id=user.id, access_group=group))
        db.commit()
        print(f"Created dev user {user.id}")


if __name__ == "__main__":
    main()