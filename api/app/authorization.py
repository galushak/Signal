from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import User

DISTRICT = "district"
BUILDING = "building"
PLAYER = "player"
ZONE = "zone"

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
USER = "user"
UPLOADER_CREATOR = "uploader_creator"
ROLES = {SUPER_ADMIN, ADMIN, USER, UPLOADER_CREATOR}

CAPABILITIES = {
    "view", "create_content", "edit_content", "trash_content", "upload_media",
    "manage_media", "publish", "schedule", "expire", "restore_versions",
    "view_audit_log", "publish_banner", "publish_takeover", "manage_players",
    "restart_players", "update_players", "manage_users", "manage_permissions",
    "manage_layouts", "manage_templates", "manage_settings", "manage_backups",
}
CREATOR_CAPABILITIES = {"view", "create_content", "edit_content", "trash_content", "upload_media", "manage_media", "publish", "schedule", "expire"}
ADMIN_CAPABILITIES = CAPABILITIES - {"manage_users", "manage_permissions", "manage_backups"}
ROLE_CAPABILITIES = {
    SUPER_ADMIN: CAPABILITIES,
    ADMIN: ADMIN_CAPABILITIES,
    USER: {"view"},
    UPLOADER_CREATOR: CREATOR_CAPABILITIES,
}


def normalized_role(user: User) -> str:
    # Retain legacy super-admin accounts during the database migration window.
    if user.super_admin:
        return SUPER_ADMIN
    return user.role if user.role in ROLES else USER


def allowed(user: User, capability: str, scope_type: str = DISTRICT, scope_id: str | None = None, db: Session | None = None) -> bool:
    return capability in ROLE_CAPABILITIES[normalized_role(user)]


def require(user: User, capability: str, scope_type: str, scope_id: str | None, db: Session) -> None:
    if not allowed(user, capability, scope_type, scope_id, db):
        raise HTTPException(status_code=403, detail="You don't have permission to do that here.")


def visible_player_ids(user: User, db: Session) -> set[str] | None:
    return None if allowed(user, "view", DISTRICT, None, db) else set()


def visible_building_ids(user: User, db: Session) -> set[str] | None:
    return None if allowed(user, "view", DISTRICT, None, db) else set()
