"""Passwords, tokens and input rules. Small, dependency-light, easy to test.

- Passwords: Argon2id (argon2-cffi). Never stored or logged in plain text.
- Access token: short-lived JWT (15 min), algorithm pinned to HS256.
- Refresh token: random string sent as an httpOnly cookie; only its SHA-256 is stored.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

ALGORITHM = "HS256"
ISSUER = "orderdesk"
_ph = PasswordHasher()  # Argon2id with the library's recommended parameters
# hashed once at import: lets login spend the same time when the email doesn't exist
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))

ROLES = ("reviewer", "admin")
NAME_RE = re.compile(r"^[\w .'-]{2,80}$")  # simple fixed format: regex is fine here
MIN_PASSWORD, MAX_PASSWORD = 12, 128
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789012", "qwertyuiop", "letmein123",
    "iloveyou123", "welcome123", "admin123456", "passw0rd1234", "abc123456789", "qwerty123456",
    "orderdesk123", "changeme1234", "football1234", "liverpool123", "1q2w3e4r5t6y",
}


# ---------------------------------------------------------------- passwords
def password_problem(password: str, email: str = "") -> str | None:
    """NIST SP 800-63B style: length and a blocklist, no 'one symbol' composition rules."""
    if len(password) < MIN_PASSWORD:
        return f"password must be at least {MIN_PASSWORD} characters"
    if len(password) > MAX_PASSWORD:
        return f"password must be at most {MAX_PASSWORD} characters"
    low = password.lower()
    if low in COMMON_PASSWORDS or len(set(low)) < 4:
        return "password is too common or too simple"
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in low:
        return "password must not contain your email name"
    return None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-time check. With no user, still hashes so timing doesn't reveal the email exists."""
    try:
        return _ph.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _ph.check_needs_rehash(stored_hash)


# ---------------------------------------------------------------- tokens
def now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, role: str, token_version: int) -> str:
    s = get_settings()
    issued = now()
    claims = {"sub": str(user_id), "role": role, "ver": token_version, "iss": ISSUER,
              "iat": issued, "exp": issued + timedelta(minutes=s.ACCESS_TOKEN_MINUTES),
              "jti": secrets.token_hex(8)}
    return jwt.encode(claims, s.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError for anything wrong: bad signature, expired, wrong alg, missing claims."""
    return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[ALGORITHM], issuer=ISSUER,
                      options={"require": ["exp", "iat", "sub", "iss"]})


def new_refresh_token() -> tuple[str, str]:
    """Returns (token for the cookie, hash for the database)."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
