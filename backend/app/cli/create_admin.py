"""Create an admin (there is no sign-up page), or reset a forgotten password.

    python -m app.cli.create_admin admin@example.com "Your Name"
    python -m app.cli.create_admin --reset admin@example.com
    python -m app.cli.create_admin --list
Prompts for the password so it never appears in shell history.
A reset logs out every session of that user and clears any lockout.
"""
import getpass
import sys

from sqlalchemy import select

from app.auth.security import hash_password, password_problem
from app.db.models import User
from app.db.session import SessionLocal


def ask_password(email: str) -> str:
    pw = getpass.getpass("password: ")
    problem = password_problem(pw, email)
    if problem:
        sys.exit(problem)
    if pw != getpass.getpass("again: "):
        sys.exit("passwords do not match")
    return pw


def create(email: str, name: str) -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit("that user already exists (use --reset to set a new password)")
        db.add(User(email=email, full_name=name, role="admin", password_hash=hash_password(ask_password(email)),
                    must_change_password=False))
        db.commit()
    print(f"admin {email} created")


def reset(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            sys.exit("no such user (use --list to see them)")
        user.password_hash = hash_password(ask_password(email))
        user.token_version += 1            # existing tokens stop working
        user.failed_logins, user.locked_until, user.is_active = 0, None, True
        db.commit()
    print(f"password reset for {email}; all their sessions are logged out")


def list_users() -> None:
    with SessionLocal() as db:
        for u in db.scalars(select(User).order_by(User.id)):
            print(f"{u.email:<40} {u.role:<9} {'active' if u.is_active else 'disabled'}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--list"]:
        list_users()
    elif len(args) == 2 and args[0] == "--reset":
        reset(args[1].lower().strip())
    elif len(args) == 2 and not args[0].startswith("--"):
        create(args[0].lower().strip(), args[1])
    else:
        sys.exit(__doc__)
