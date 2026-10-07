import argparse
import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import AccessGroup, AdminScope, Role, User
from app.db.session import SessionLocal


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in Role])
    p.add_argument("--admin-groups", default="", help="comma-separated, e.g. hr,general")
    args = p.parse_args()

    password = getpass.getpass("Password: ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")

    with SessionLocal() as db:
        email = args.email.lower()
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("User already exists")
        user = User(email=email, password_hash=hash_password(password), role=Role(args.role))
        db.add(user)
        db.flush()
        for g in filter(None, args.admin_groups.split(",")):
            db.add(AdminScope(user_id=user.id, access_group=AccessGroup(g.strip())))
        db.commit()
        print(f"Created {email} ({args.role})")


if __name__ == "__main__":
    main()