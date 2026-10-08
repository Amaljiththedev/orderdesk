"""Create the first admin (there is no sign-up page).

    python -m app.cli.create_admin admin@example.com "Your Name"
Prompts for the password so it never appears in shell history.
"""
import getpass
import sys

from sqlalchemy import select

from app.auth.security import hash_password, password_problem
from app.db.models import User
from app.db.session import SessionLocal


def main(email: str, name: str) -> None:
    email = email.lower().strip()
    pw = getpass.getpass("password: ")
    problem = password_problem(pw, email)
    if problem:
        sys.exit(problem)
    if pw != getpass.getpass("again: "):
        sys.exit("passwords do not match")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit("that user already exists")
        db.add(User(email=email, full_name=name, role="admin", password_hash=hash_password(pw),
                    must_change_password=False))
        db.commit()
    print(f"admin {email} created")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
