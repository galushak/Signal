from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PermissionGrant, Player, User

DISTRICT = "district"
BUILDING = "building"
PLAYER = "player"


def _matches_scope(grant: PermissionGrant, scope_type: str, scope_id: str | None, db: Session) -> bool:
    if grant.scope_type == DISTRICT:
        return True
    if grant.scope_type == scope_type and grant.scope_id == scope_id:
        return True
    if grant.scope_type == BUILDING and scope_type == PLAYER:
        player = db.get(Player, scope_id)
        return bool(player and player.building_id == grant.scope_id)
    return False


def allowed(user: User, capability: str, scope_type: str = DISTRICT, scope_id: str | None = None, db: Session | None = None) -> bool:
    if user.super_admin:
        return True
    if db is None:
        return False
    grants = db.scalars(select(PermissionGrant).where(PermissionGrant.user_id == user.id, PermissionGrant.capability == capability)).all()
    return any(_matches_scope(grant, scope_type, scope_id, db) for grant in grants)


def require(user: User, capability: str, scope_type: str, scope_id: str | None, db: Session) -> None:
    if not allowed(user, capability, scope_type, scope_id, db):
        raise HTTPException(status_code=403, detail="You don't have permission to do that here.")


def visible_player_ids(user: User, db: Session) -> set[str] | None:
    if user.super_admin or allowed(user, "view", DISTRICT, None, db):
        return None
    grants = db.scalars(select(PermissionGrant).where(PermissionGrant.user_id == user.id, PermissionGrant.capability == "view")).all()
    ids: set[str] = {g.scope_id for g in grants if g.scope_type == PLAYER and g.scope_id}
    building_ids = [g.scope_id for g in grants if g.scope_type == BUILDING and g.scope_id]
    if building_ids:
        ids.update(db.scalars(select(Player.id).where(Player.building_id.in_(building_ids))).all())
    return ids


def visible_building_ids(user: User, db: Session) -> set[str] | None:
    if user.super_admin or allowed(user, "view", DISTRICT, None, db):
        return None
    grants = db.scalars(select(PermissionGrant).where(PermissionGrant.user_id == user.id, PermissionGrant.capability == "view")).all()
    ids = {g.scope_id for g in grants if g.scope_type == BUILDING and g.scope_id}
    player_ids = [g.scope_id for g in grants if g.scope_type == PLAYER and g.scope_id]
    if player_ids:
        ids.update(db.scalars(select(Player.building_id).where(Player.id.in_(player_ids))).all())
    return ids
