"""FastAPI dependencies: who is calling, and are they allowed."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)
UNAUTHORISED = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated",
                             headers={"WWW-Authenticate": "Bearer"})


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise UNAUTHORISED
    try:
        claims = decode_access_token(creds.credentials)
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise UNAUTHORISED
    user = db.get(User, user_id)
    # role and version come from the database, not from the token: a demoted or logged-out
    # user loses access immediately, even with a token that hasn't expired yet
    if not user or not user.is_active or claims.get("ver") != user.token_version:
        raise UNAUTHORISED
    return user


def require_role(*roles: str):
    def check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for your role")
        return user
    return check


require_admin = require_role("admin")
