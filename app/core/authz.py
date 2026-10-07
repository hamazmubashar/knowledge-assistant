from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import AccessGroup, AdminScope, Document, RoleGroupAccess, User


def readable_groups(db, user: User) -> set[AccessGroup]:
    return set(db.scalars(select(RoleGroupAccess.access_group)
                          .where(RoleGroupAccess.role == user.role)))


def admin_groups(db, user: User) -> set[AccessGroup]:
    return set(db.scalars(select(AdminScope.access_group)
                          .where(AdminScope.user_id == user.id)))


def can_manage(db, user: User, group: AccessGroup) -> bool:
    return group in admin_groups(db, user)


def ensure_can_view(db, user: User, doc: Document | None) -> None:
    if doc is None or doc.is_deleted:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.access_group in readable_groups(db, user) or can_manage(db, user, doc.access_group):
        return
    raise HTTPException(status_code=404, detail="Not found")