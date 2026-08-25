from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PermissionGrant, Player, User, Zone

DISTRICT = "district"
BUILDING = "building"
PLAYER = "player"
ZONE = "zone"


def _matches_scope(grant: PermissionGrant, scope_type: str, scope_id: str | None, db: Session) -> bool:
    if grant.scope_type == DISTRICT:
        return True
    if grant.scope_type == scope_type and grant.scope_id == scope_id:
        return True
    if grant.scope_type == BUILDING and scope_type == PLAYER:
        player = db.get(Player, scope_id)
        return bool(player and player.building_id == grant.scope_id)
    if scope_type == ZONE:
        zone = db.get(Zone, scope_id)
        if not zone:
            return False
        if grant.scope_type == PLAYER:
            return bool(db.scalar(select(Player.id).where(Player.id == grant.scope_id, Player.layout_id == zone.layout_id)))
        if grant.scope_type == BUILDING:
            return bool(db.scalar(select(Player.id).where(Player.building_id == grant.scope_id, Player.layout_id == zone.layout_id)))
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
