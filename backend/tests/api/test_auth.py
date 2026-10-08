"""Auth through the real API (FastAPI TestClient + real database)."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.auth.security import create_access_token, hash_password, password_problem
from app.config import get_settings
from app.db.models import AuditLog, RefreshToken, User
from app.db.session import SessionLocal
from app.main import app

PW = "correct horse battery staple"


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    auth_api._ip_hits.clear()


@pytest.fixture
def make_user():
    made = []

    def _make(role="reviewer", active=True):
        email = f"t-{uuid.uuid4().hex[:10]}@example.com"
        with SessionLocal() as db:
            u = User(email=email, full_name="Test User", role=role, is_active=active,
                     password_hash=hash_password(PW), must_change_password=False)
            db.add(u)
            db.commit()
            made.append(u.id)
            return u
    yield _make
    with SessionLocal() as db:
        for uid in made:
            db.query(AuditLog).filter(AuditLog.entity == "user", AuditLog.entity_id == uid).delete()
            db.query(RefreshToken).filter(RefreshToken.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
        db.commit()


def client():
    return TestClient(app)


def login(c, email, pw=PW):
    return c.post("/auth/login", json={"email": email, "password": pw})


def test_login_and_me(make_user):
    u = make_user()
    c = client()
    r = login(c, u.email.upper())                 # email is case-insensitive
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert "od_refresh" in r.cookies
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == u.email


def test_wrong_password_and_unknown_email_look_the_same(make_user):
    u = make_user()
    c = client()
    a = login(c, u.email, "wrong password here")
    b = login(c, "nobody-here@example.com", "wrong password here")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_repeated_failures(make_user):
    u = make_user()
    c = client()
    for _ in range(get_settings().MAX_FAILED_LOGINS):
        assert login(c, u.email, "wrong password here").status_code == 401
    assert login(c, u.email).status_code == 429     # even the right password is refused while locked


def test_protected_routes_need_a_token():
    c = client()
    assert c.get("/documents").status_code == 401
    assert c.get("/products/search", params={"q": "elbow"}).status_code == 401
    assert c.get("/health").status_code == 200


@pytest.mark.parametrize("bad", ["expired", "tampered", "alg_none", "garbage"])
def test_bad_tokens_rejected(make_user, bad):
    u = make_user()
    s = get_settings()
    if bad == "expired":
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        tok = jwt.encode({"sub": str(u.id), "ver": 0, "iss": "orderdesk", "iat": past, "exp": past},
                         s.JWT_SECRET, algorithm="HS256")
    elif bad == "tampered":
        tok = create_access_token(u.id, "reviewer", 0)[:-3] + "abc"
    elif bad == "alg_none":
        tok = jwt.encode({"sub": str(u.id), "ver": 0, "iss": "orderdesk"}, None, algorithm="none")
    else:
        tok = "not.a.token"
    assert client().get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_reviewer_cannot_use_admin_routes(make_user):
    u = make_user("reviewer")
    tok = login(client(), u.email).json()["access_token"]
    assert client().get("/users", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_refresh_rotates_and_reuse_revokes_everything(make_user):
    u = make_user()
    c = client()
    login(c, u.email)
    old = c.cookies.get("od_refresh")
    r1 = c.post("/auth/refresh")
    assert r1.status_code == 200 and c.cookies.get("od_refresh") != old
    new_access = r1.json()["access_token"]
    # replay the old (already rotated) cookie: looks like theft
    thief = client()
    thief.cookies.set("od_refresh", old, path="/auth")
    assert thief.post("/auth/refresh").status_code == 401
    # ...so the legitimate session is ended too
    assert c.post("/auth/refresh").status_code == 401
    assert client().get("/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 401


def test_change_password_logs_out_other_sessions(make_user):
    u = make_user()
    a, b = client(), client()
    tok_a = login(a, u.email).json()["access_token"]
    tok_b = login(b, u.email).json()["access_token"]
    r = a.post("/auth/change-password", headers={"Authorization": f"Bearer {tok_a}"},
               json={"current_password": PW, "new_password": "a much longer new passphrase"})
    assert r.status_code == 200
    assert client().get("/auth/me", headers={"Authorization": f"Bearer {tok_b}"}).status_code == 401
    assert client().get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_deactivated_user_cannot_log_in(make_user):
    u = make_user(active=False)
    assert login(client(), u.email).status_code == 401


@pytest.mark.parametrize("pw,ok", [
    ("short", False), ("password123", False), ("aaaaaaaaaaaaaaaa", False),
    ("ama.thomas.liverpool", False), ("correct horse battery staple", True),
])
def test_password_rules(pw, ok):
    assert (password_problem(pw, "ama.thomas@example.com") is None) is ok


def test_invalid_email_rejected():
    assert client().post("/auth/login", json={"email": "not-an-email", "password": "x"}).status_code == 422
