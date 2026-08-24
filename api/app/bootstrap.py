import argparse

from sqlalchemy import select

from .auth import hash_password
from .database import SessionLocal
from .models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Signal's first Super Admin.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if len(args.password) < 12:
        raise SystemExit("Use a password with at least 12 characters.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username.lower())):
            raise SystemExit("That username already exists.")
        db.add(User(username=args.username.lower(), display_name=args.display_name, password_hash=hash_password(args.password), super_admin=True))
        db.commit()
    print("Super Admin created.")


if __name__ == "__main__":
    main()
