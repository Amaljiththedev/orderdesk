"""User management. Admin only; there is no public sign-up."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import audit, revoke_all, user_out
from app.auth.deps import require_admin
from app.auth.security import NAME_RE, hash_password, password_problem
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])
Role = Literal["reviewer", "admin"]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(pattern=NAME_RE.pattern)
    role: Role = "reviewer"
    temporary_password: str = Field(min_length=1, max_length=256)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, pattern=NAME_RE.pattern)
    role: Role | None = None
    is_active: bool | None = None


@router.get("")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{**user_out(u), "is_active": u.is_active, "last_login_at": u.last_login_at}
            for u in db.scalars(select(User).order_by(User.id))]


@router.post("", status_code=201)
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with this email already exists")
    problem = password_problem(body.temporary_password, email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    u = User(email=email, full_name=body.full_name.strip(), role=body.role,
             password_hash=hash_password(body.temporary_password), must_change_password=True)
    db.add(u)
    db.flush()
    audit(db, admin.email, "user_created", u.id, role=u.role)
    db.commit()
    return user_out(u)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    removing_admin = (body.role == "reviewer" or body.is_active is False) and u.role == "admin"
    if removing_admin:
        admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active))
        if admins <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "there must be at least one active admin")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(u, k, v)
    if "role" in changes or changes.get("is_active") is False:
        revoke_all(db, u)  # new role or deactivation takes effect immediately
    audit(db, admin.email, "user_updated", u.id, **changes)
    db.commit()
    return {**user_out(u), "is_active": u.is_active}
