"""One-off CLI to bootstrap the first platform-admin account.

There is deliberately no HTTP endpoint for this -- a public
"become platform admin" route would be a critical vulnerability. Run this
directly against the target database instead:

    python scripts/create_platform_admin.py admin@nornetorg.no

Prompts for a password interactively (never pass it as an argument -- it
would end up in shell history).
"""

import getpass
import sys

sys.path.insert(0, ".")

from database import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402
from routers.auth import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_platform_admin.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    password = getpass.getpass("Passord: ")
    confirm = getpass.getpass("Bekreft passord: ")
    if password != confirm:
        print("Passordene er ikke like.")
        sys.exit(1)
    if len(password) < 8:
        print("Passordet må være minst 8 tegn.")
        sys.exit(1)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"En bruker med e-post {email} finnes allerede.")
            sys.exit(1)

        admin = User(
            email=email,
            password_hash=hash_password(password),
            is_platform_admin=True,
        )
        db.add(admin)
        db.commit()
        print(f"Plattformadmin opprettet: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
