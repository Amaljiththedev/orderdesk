"""Login, token refresh, logout, me, change password.

Error messages are deliberately vague ("invalid email or password") so the API never tells an
attacker which emails exist. Every security event is written to audit_log.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import (create_access_token, hash_password, hash_refresh_token, needs_rehash,
                               new_refresh_token, now, password_problem, verify_password)
from app.config import get_settings
from app.db.models import AuditLog, RefreshToken, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "od_refresh"
BAD_LOGIN = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
SLOW_DOWN = HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts, try again later")

# per-IP limit, in memory. Fine for one API process; with several, move this to Redis.
_IP_WINDOW_S, _IP_MAX = 15 * 60, 30
_ip_hits: dict[str, deque] = defaultdict(deque)


def _ip_limited(ip: str) -> bool:
    q, t = _ip_hits[ip], time.monotonic()
    while q and t - q[0] > _IP_WINDOW_S:
        q.popleft()
    q.append(t)
    return len(q) > _IP_MAX


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
            "must_change_password": u.must_change_password}


def audit(db: Session, actor: str, action: str, user_id: int, **after) -> None:
    db.add(AuditLog(actor=actor, action=action, entity="user", entity_id=user_id, after=after or None))


def _issue(db: Session, response: Response, user: User) -> tuple[dict, RefreshToken]:
    """Access token in the body, refresh token in an httpOnly cookie."""
    s = get_settings()
    token, token_hash = new_refresh_token()
    row = RefreshToken(user_id=user.id, token_hash=token_hash,
                       expires_at=now() + timedelta(days=s.REFRESH_TOKEN_DAYS))
    db.add(row)
    db.flush()
    response.set_cookie(COOKIE, token, httponly=True, secure=s.ENV != "dev", samesite="strict",
                        max_age=s.REFRESH_TOKEN_DAYS * 86400, path="/auth")
    return {"access_token": create_access_token(user.id, user.role, user.token_version),
            "token_type": "bearer", "expires_in": s.ACCESS_TOKEN_MINUTES * 60, "user": user_out(user)}, row


def revoke_all(db: Session, user: User) -> None:
    """Log the user out everywhere: old access tokens stop working (version bump), refresh tokens revoked."""
    user.token_version += 1
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=now()))


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    if _ip_limited(request.client.host if request.client else "unknown"):
        raise SLOW_DOWN
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))

    if user and user.locked_until and user.locked_until > now():
        audit(db, email, "login_blocked_locked", user.id)
        db.commit()
        raise SLOW_DOWN

    ok = verify_password(user.password_hash if user else None, body.password)  # same cost either way
    if not ok or not user or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= s.MAX_FAILED_LOGINS:
                user.locked_until = now() + timedelta(minutes=s.LOCKOUT_MINUTES)
                user.failed_logins = 0
                audit(db, email, "account_locked", user.id)
            audit(db, email, "login_failed", user.id)
            db.commit()
        raise BAD_LOGIN

    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now()
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    out, _ = _issue(db, response, user)
    audit(db, email, "login", user.id)
    db.commit()
    return out


@router.post("/refresh")
def refresh(response: Response, od_refresh: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not od_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(od_refresh)))
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session")
    user = db.get(User, row.user_id)
    if row.revoked_at is not None:
        # a rotated token came back: it was copied somewhere. Treat as theft, end every session.
        revoke_all(db, user)
        audit(db, user.email, "refresh_token_reuse_detected", user.id)
        db.commit()
        response.delete_cookie(COOKIE, path="/auth")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session revoked")
    if row.expires_at < now() or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    out, new_row = _issue(db, response, user)
    row.revoked_at, row.replaced_by = now(), new_row.id   # rotation: each refresh token works once
    db.commit()
    return out


@router.post("/logout", status_code=204)
def logout(response: Response, od_refresh: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if od_refresh:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(od_refresh)))
        if row and row.revoked_at is None:
            row.revoked_at = now()
            audit(db, str(row.user_id), "logout", row.user_id)
            db.commit()
    response.delete_cookie(COOKIE, path="/auth")


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, response: Response, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password is wrong")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    revoke_all(db, user)                        # every other session ends
    out, _ = _issue(db, response, user)         # this one continues with a fresh token
    audit(db, user.email, "password_changed", user.id)
    db.commit()
    return out
