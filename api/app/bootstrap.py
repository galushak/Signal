import argparse

from datetime import UTC, datetime

from sqlalchemy import select

from .auth import hash_password, password_policy_error
from .database import SessionLocal
from .models import AppSettings, Layout, User, Zone


FULL_SCREEN_LAYOUT_ID = "00000000-0000-4000-8000-000000000001"
FULL_SCREEN_MAIN_ZONE_ID = "00000000-0000-4000-8000-000000000002"


def ensure_full_screen_layout(db, user: User) -> None:
    """Seed the protected fallback after the first admin on a new install."""
    if db.scalar(select(Layout).where(Layout.system_key == "full-screen")):
        return
    layout = Layout(
        id=FULL_SCREEN_LAYOUT_ID,
        name="Full Screen",
        description="Signal system fallback layout.",
        logical_width=1920,
        logical_height=1080,
        enabled=True,
        locked=True,
        system_key="full-screen",
        created_by_id=user.id,
    )
    db.add(layout)
    db.flush()
    db.add(Zone(
        id=FULL_SCREEN_MAIN_ZONE_ID,
        layout_id=layout.id,
        name="Main",
        x=0,
        y=0,
        width=1920,
        height=1080,
        z_index=0,
        enabled=True,
        locked=True,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Signal's first Super Admin.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if error := password_policy_error(args.password):
        raise SystemExit(error)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username.lower())):
            raise SystemExit("That username already exists.")
        user = User(username=args.username.lower(), display_name=args.display_name, password_hash=hash_password(args.password), super_admin=True)
        db.add(user)
        db.flush()
        app_settings = db.get(AppSettings, 1)
        if app_settings is None:
            app_settings = AppSettings(id=1, organization_name="Signal", setup_completed_at=datetime.now(UTC))
            db.add(app_settings)
        else:
            app_settings.setup_completed_at = app_settings.setup_completed_at or datetime.now(UTC)
        ensure_full_screen_layout(db, user)
        db.commit()
    print("Super Admin created.")


if __name__ == "__main__":
    main()
