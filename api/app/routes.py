import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth
from .audit import record
from .authorization import BUILDING, DISTRICT, PLAYER, allowed, require, visible_building_ids, visible_player_ids
from .database import get_db
from .models import AuditEvent, Building, MediaAsset, MediaAssetTag, MediaFolder, PermissionGrant, Player, Tag, User
from .settings import get_settings
from .worker import prepare_media

router = APIRouter(prefix="/api/v1")
settings = get_settings()
CAPABILITIES = {"view", "create_content", "edit_content", "trash_content", "upload_media", "manage_media", "publish", "schedule", "expire", "restore_versions", "view_audit_log", "publish_banner", "publish_takeover", "manage_players", "restart_players", "update_players", "manage_users", "manage_permissions", "manage_layouts", "manage_templates", "manage_settings", "manage_backups"}


class LoginInput(BaseModel):
    username: str
    password: str


class PasswordInput(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class UserInput(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=256)
    enabled: bool = True
    super_admin: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    super_admin: bool | None = None


class GrantInput(BaseModel):
    capability: str
    scope_type: str = DISTRICT
    scope_id: str | None = None


class BuildingInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    enabled: bool = True


class PlayerInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    building_id: str
    description: str | None = None
    enabled: bool = True
    resolution: str | None = None


class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    scope_type: str = DISTRICT
    scope_id: str | None = None


def user_data(user: User, db: Session | None = None) -> dict:
    grants = [] if db is None else [{"id": g.id, "capability": g.capability, "scope_type": g.scope_type, "scope_id": g.scope_id} for g in user.grants]
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "enabled": user.enabled, "super_admin": user.super_admin, "last_login_at": user.last_login_at, "created_at": user.created_at, "grants": grants}


def building_data(building: Building) -> dict:
    return {"id": building.id, "name": building.name, "description": building.description, "enabled": building.enabled, "created_at": building.created_at, "updated_at": building.updated_at}


def player_data(player: Player) -> dict:
    connected = player.last_seen_at is not None
    return {"id": player.id, "name": player.name, "building_id": player.building_id, "building_name": player.building.name, "description": player.description, "enabled": player.enabled, "enrollment_status": player.enrollment_status, "last_seen_at": player.last_seen_at, "software_version": player.software_version, "resolution": player.resolution, "health_state": player.health_state if connected else "never_connected", "cache_state": player.cache_state, "created_at": player.created_at, "updated_at": player.updated_at}


def media_data(asset: MediaAsset, db: Session) -> dict:
    tag_names = db.scalars(select(Tag.name).join(MediaAssetTag, Tag.id == MediaAssetTag.tag_id).where(MediaAssetTag.asset_id == asset.id)).all()
    return {"id": asset.id, "display_name": asset.display_name, "original_filename": asset.original_filename, "media_type": asset.media_type, "mime_type": asset.mime_type, "file_size": asset.file_size, "processing_state": asset.processing_state, "processing_error": asset.processing_error, "width": asset.width, "height": asset.height, "duration_seconds": asset.duration_seconds, "scope_type": asset.scope_type, "scope_id": asset.scope_id, "folder_id": asset.folder_id, "uploaded_by_id": asset.uploaded_by_id, "created_at": asset.created_at, "trashed_at": asset.trashed_at, "tags": tag_names, "file_url": f"/api/v1/media/{asset.id}/file", "thumbnail_url": f"/api/v1/media/{asset.id}/thumbnail" if asset.thumbnail_path else None}


def scope_valid(scope_type: str, scope_id: str | None, db: Session) -> None:
    if scope_type not in {DISTRICT, BUILDING, PLAYER}:
        raise HTTPException(status_code=422, detail="Choose District, Building, or Player for access.")
    if scope_type == DISTRICT and scope_id is not None:
        raise HTTPException(status_code=422, detail="District access does not need a specific item.")
    if scope_type == BUILDING and (not scope_id or not db.get(Building, scope_id)):
        raise HTTPException(status_code=422, detail="Choose a valid building.")
    if scope_type == PLAYER and (not scope_id or not db.get(Player, scope_id)):
        raise HTTPException(status_code=422, detail="Choose a valid player.")


def media_type_for(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").lower()
    if content_type in {"image/jpeg", "image/png", "image/webp"}:
        return "image"
    if content_type == "application/pdf":
        return "pdf"
    if content_type.startswith("video/"):
        return "video"
    raise HTTPException(status_code=415, detail="Use a JPEG, PNG, WebP, PDF, or video file.")


@router.post("/auth/login")
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    auth.check_login_rate_limit(f"{auth.client_ip(request)}:{username}")
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.enabled or not auth.verify_password(payload.password, user.password_hash):
        record(db, actor=user, action="auth.login_failed", resource_type="user", resource_id=user.id if user else None, resource_name=username, source_ip=auth.client_ip(request))
        db.commit()
        raise HTTPException(status_code=401, detail="Your username or password is incorrect.")
    token, _ = auth.create_session(db, user)
    user.last_login_at = datetime.now(UTC)
    record(db, actor=user, action="auth.login", resource_type="user", resource_id=user.id, resource_name=user.display_name, source_ip=auth.client_ip(request))
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": user_data(user, db)}


@router.post("/auth/logout")
def logout(request: Request, user: User = Depends(auth.get_current_user), session=Depends(auth.current_session), db: Session = Depends(get_db)):
    session.revoked_at = datetime.now(UTC)
    record(db, actor=user, action="auth.logout", resource_type="user", resource_id=user.id, source_ip=auth.client_ip(request))
    db.commit()
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return user_data(user, db)


@router.post("/auth/change-password")
def change_password(payload: PasswordInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    user.password_hash = auth.hash_password(payload.password)
    record(db, actor=user, action="auth.password_changed", resource_type="user", resource_id=user.id, source_ip=auth.client_ip(request))
    db.commit()
    return {"ok": True}


@router.get("/dashboard")
def dashboard(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player_ids = visible_player_ids(user, db)
    players_query = select(Player)
    if player_ids is not None:
        players_query = players_query.where(Player.id.in_(player_ids)) if player_ids else players_query.where(False)
    players = db.scalars(players_query).all()
    media_count = sum(1 for asset in db.scalars(select(MediaAsset).where(MediaAsset.trashed_at.is_(None))).all() if allowed(user, "view", asset.scope_type, asset.scope_id, db))
    return {"players_total": len(players), "players_never_connected": sum(p.last_seen_at is None for p in players), "players_online": sum(p.health_state == "online" and p.last_seen_at is not None for p in players), "media_total": media_count, "warnings": [{"kind": "never_connected", "player": player_data(p)} for p in players if p.last_seen_at is None][:5]}


@router.get("/buildings")
def list_buildings(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    ids = visible_building_ids(user, db)
    query = select(Building).order_by(Building.name)
    if ids is not None:
        query = query.where(Building.id.in_(ids)) if ids else query.where(False)
    return [building_data(item) for item in db.scalars(query)]


@router.post("/buildings", status_code=201)
def create_building(payload: BuildingInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_settings", DISTRICT, None, db)
    if db.scalar(select(Building).where(Building.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="A building with that name already exists.")
    building = Building(name=payload.name.strip(), description=payload.description, enabled=payload.enabled)
    db.add(building); db.flush()
    record(db, actor=user, action="building.created", resource_type="building", resource_id=building.id, resource_name=building.name, scope_type=BUILDING, scope_id=building.id, source_ip=auth.client_ip(request))
    db.commit(); db.refresh(building)
    return building_data(building)


@router.patch("/buildings/{building_id}")
def update_building(building_id: str, payload: BuildingInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_settings", DISTRICT, None, db)
    building = db.get(Building, building_id)
    if not building: raise HTTPException(status_code=404, detail="Building not found.")
    before = {"name": building.name, "enabled": building.enabled}
    building.name, building.description, building.enabled = payload.name.strip(), payload.description, payload.enabled
    record(db, actor=user, action="building.updated", resource_type="building", resource_id=building.id, resource_name=building.name, scope_type=BUILDING, scope_id=building.id, source_ip=auth.client_ip(request), metadata={"before": before})
    db.commit(); db.refresh(building); return building_data(building)


@router.get("/players")
def list_players(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    ids = visible_player_ids(user, db); query = select(Player).order_by(Player.name)
    if ids is not None: query = query.where(Player.id.in_(ids)) if ids else query.where(False)
    return [player_data(item) for item in db.scalars(query)]


@router.post("/players", status_code=201)
def create_player(payload: PlayerInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    scope_valid(BUILDING, payload.building_id, db); require(user, "manage_players", BUILDING, payload.building_id, db)
    player = Player(name=payload.name.strip(), building_id=payload.building_id, description=payload.description, enabled=payload.enabled, resolution=payload.resolution)
    db.add(player); db.flush()
    record(db, actor=user, action="player.created", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit(); db.refresh(player); return player_data(player)


@router.patch("/players/{player_id}")
def update_player(player_id: str, payload: PlayerInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "manage_players", PLAYER, player.id, db); scope_valid(BUILDING, payload.building_id, db)
    player.name, player.building_id, player.description, player.enabled, player.resolution = payload.name.strip(), payload.building_id, payload.description, payload.enabled, payload.resolution
    record(db, actor=user, action="player.updated", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit(); db.refresh(player); return player_data(player)


@router.post("/players/{player_id}/enrollment-code")
def issue_enrollment_code(player_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "manage_players", PLAYER, player.id, db)
    code = secrets.token_urlsafe(8).upper()
    player.enrollment_status, player.enrollment_code_hash, player.enrollment_expires_at = "pending", auth.hash_password(code), datetime.now(UTC) + timedelta(minutes=30)
    record(db, actor=user, action="player.enrollment_code_issued", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit(); return {"code": code, "expires_at": player.enrollment_expires_at}


@router.get("/users")
def list_users(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_users", DISTRICT, None, db)
    return [user_data(item, db) for item in db.scalars(select(User).order_by(User.display_name))]


@router.post("/users", status_code=201)
def create_user(payload: UserInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_users", DISTRICT, None, db)
    username = payload.username.lower()
    if db.scalar(select(User).where(User.username == username)): raise HTTPException(status_code=409, detail="That username is already in use.")
    new_user = User(username=username, display_name=payload.display_name.strip(), password_hash=auth.hash_password(payload.password), enabled=payload.enabled, super_admin=payload.super_admin)
    db.add(new_user); db.flush(); record(db, actor=user, action="user.created", resource_type="user", resource_id=new_user.id, resource_name=new_user.display_name, source_ip=auth.client_ip(request)); db.commit(); db.refresh(new_user); return user_data(new_user, db)


@router.patch("/users/{target_id}")
def update_user(target_id: str, payload: UserUpdate, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_users", DISTRICT, None, db); target = db.get(User, target_id)
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    if payload.display_name is not None: target.display_name = payload.display_name.strip()
    if payload.enabled is not None: target.enabled = payload.enabled
    if payload.super_admin is not None: target.super_admin = payload.super_admin
    record(db, actor=user, action="user.updated", resource_type="user", resource_id=target.id, resource_name=target.display_name, source_ip=auth.client_ip(request)); db.commit(); db.refresh(target); return user_data(target, db)


@router.post("/users/{target_id}/reset-password")
def reset_password(target_id: str, payload: PasswordInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_users", DISTRICT, None, db); target = db.get(User, target_id)
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    target.password_hash = auth.hash_password(payload.password)
    db.query(auth.AuthSession).filter(auth.AuthSession.user_id == target.id).update({"revoked_at": datetime.now(UTC)})
    record(db, actor=user, action="user.password_reset", resource_type="user", resource_id=target.id, resource_name=target.display_name, source_ip=auth.client_ip(request)); db.commit(); return {"ok": True}


@router.post("/users/{target_id}/grants", status_code=201)
def add_grant(target_id: str, payload: GrantInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_permissions", DISTRICT, None, db)
    if payload.capability not in CAPABILITIES: raise HTTPException(status_code=422, detail="That permission is not recognized.")
    scope_valid(payload.scope_type, payload.scope_id, db); target = db.get(User, target_id)
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    grant = PermissionGrant(user_id=target.id, capability=payload.capability, scope_type=payload.scope_type, scope_id=payload.scope_id)
    db.add(grant); db.flush(); record(db, actor=user, action="permission.granted", resource_type="user", resource_id=target.id, resource_name=target.display_name, scope_type=payload.scope_type, scope_id=payload.scope_id, source_ip=auth.client_ip(request), metadata={"capability": payload.capability}); db.commit(); return {"id": grant.id}


@router.delete("/users/{target_id}/grants/{grant_id}")
def remove_grant(target_id: str, grant_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_permissions", DISTRICT, None, db); grant = db.get(PermissionGrant, grant_id)
    if not grant or grant.user_id != target_id: raise HTTPException(status_code=404, detail="Permission not found.")
    db.delete(grant); record(db, actor=user, action="permission.removed", resource_type="user", resource_id=target_id, scope_type=grant.scope_type, scope_id=grant.scope_id, source_ip=auth.client_ip(request), metadata={"capability": grant.capability}); db.commit(); return {"ok": True}


@router.get("/folders")
def list_folders(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return [{"id": item.id, "name": item.name, "parent_id": item.parent_id, "scope_type": item.scope_type, "scope_id": item.scope_id} for item in db.scalars(select(MediaFolder).order_by(MediaFolder.name)) if allowed(user, "view", item.scope_type, item.scope_id, db)]


@router.post("/folders", status_code=201)
def create_folder(payload: FolderInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    scope_valid(payload.scope_type, payload.scope_id, db); require(user, "manage_media", payload.scope_type, payload.scope_id, db)
    folder = MediaFolder(name=payload.name.strip(), parent_id=payload.parent_id, scope_type=payload.scope_type, scope_id=payload.scope_id)
    db.add(folder); db.flush(); record(db, actor=user, action="media_folder.created", resource_type="media_folder", resource_id=folder.id, resource_name=folder.name, scope_type=folder.scope_type, scope_id=folder.scope_id, source_ip=auth.client_ip(request)); db.commit(); return {"id": folder.id, "name": folder.name}


@router.get("/media")
def list_media(search: str | None = None, media_type: str | None = None, include_trashed: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    query = select(MediaAsset).order_by(MediaAsset.created_at.desc())
    if not include_trashed: query = query.where(MediaAsset.trashed_at.is_(None))
    if search: query = query.where(MediaAsset.display_name.ilike(f"%{search.strip()}%"))
    if media_type: query = query.where(MediaAsset.media_type == media_type)
    return [media_data(asset, db) for asset in db.scalars(query) if allowed(user, "view", asset.scope_type, asset.scope_id, db)]


@router.post("/media/upload", status_code=201)
async def upload_media(request: Request, files: Annotated[list[UploadFile], File(...)], scope_type: Annotated[str, Form()] = DISTRICT, scope_id: Annotated[str | None, Form()] = None, folder_id: Annotated[str | None, Form()] = None, tags: Annotated[str | None, Form()] = None, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    scope_valid(scope_type, scope_id, db); require(user, "upload_media", scope_type, scope_id, db)
    if folder_id and not db.get(MediaFolder, folder_id): raise HTTPException(status_code=422, detail="Choose a valid folder.")
    results = []
    for upload in files:
        kind = media_type_for(upload); suffix = Path(upload.filename or "").suffix.lower()
        asset_id = secrets.token_hex(16); relative = f"originals/{asset_id}{suffix}"; destination = settings.media_root / relative
        total = 0
        with destination.open("wb") as output:
            while chunk := await upload.read(1_048_576):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    output.close(); destination.unlink(missing_ok=True); raise HTTPException(status_code=413, detail="That file is larger than the upload limit.")
                output.write(chunk)
        asset = MediaAsset(id=asset_id, display_name=Path(upload.filename or "Untitled").stem[:255], original_filename=Path(upload.filename or "upload").name[:255], media_type=kind, mime_type=upload.content_type or "application/octet-stream", original_path=relative, file_size=total, scope_type=scope_type, scope_id=scope_id, folder_id=folder_id, uploaded_by_id=user.id)
        db.add(asset); db.flush()
        for tag_name in [name.strip().lower() for name in (tags or "").split(",") if name.strip()]:
            tag = db.scalar(select(Tag).where(Tag.name == tag_name)) or Tag(name=tag_name)
            db.add(tag); db.flush(); db.add(MediaAssetTag(asset_id=asset.id, tag_id=tag.id))
        record(db, actor=user, action="media.uploaded", resource_type="media", resource_id=asset.id, resource_name=asset.display_name, scope_type=scope_type, scope_id=scope_id, source_ip=auth.client_ip(request))
        results.append(asset)
    db.commit()
    for asset in results: prepare_media.delay(asset.id)
    return [media_data(asset, db) for asset in results]


def media_for_user(asset_id: str, user: User, db: Session) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="Media not found.")
    require(user, "view", asset.scope_type, asset.scope_id, db); return asset


@router.get("/media/{asset_id}/file")
def download_media(asset_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    asset = media_for_user(asset_id, user, db); path = settings.media_root / (asset.processed_path or asset.original_path)
    if not path.is_file(): raise HTTPException(status_code=404, detail="The media file is not available.")
    return FileResponse(path, media_type=asset.mime_type, filename=asset.original_filename)


@router.get("/media/{asset_id}/thumbnail")
def thumbnail(asset_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    asset = media_for_user(asset_id, user, db)
    if not asset.thumbnail_path: raise HTTPException(status_code=404, detail="A thumbnail is not ready yet.")
    return FileResponse(settings.media_root / asset.thumbnail_path, media_type="image/jpeg")


@router.post("/media/{asset_id}/trash")
def trash_media(asset_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="Media not found.")
    require(user, "trash_content", asset.scope_type, asset.scope_id, db); asset.trashed_at = datetime.now(UTC)
    record(db, actor=user, action="media.trashed", resource_type="media", resource_id=asset.id, resource_name=asset.display_name, scope_type=asset.scope_type, scope_id=asset.scope_id, source_ip=auth.client_ip(request)); db.commit(); return {"ok": True}


@router.post("/media/{asset_id}/restore")
def restore_media(asset_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="Media not found.")
    require(user, "manage_media", asset.scope_type, asset.scope_id, db); asset.trashed_at = None
    record(db, actor=user, action="media.restored", resource_type="media", resource_id=asset.id, resource_name=asset.display_name, scope_type=asset.scope_type, scope_id=asset.scope_id, source_ip=auth.client_ip(request)); db.commit(); return {"ok": True}


@router.get("/audit")
def audit_events(limit: int = 100, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "view_audit_log", DISTRICT, None, db)
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(min(max(limit, 1), 500))).all()
    return [{"id": item.id, "timestamp": item.timestamp, "action": item.action, "resource_type": item.resource_type, "resource_id": item.resource_id, "resource_name": item.resource_name, "scope_type": item.scope_type, "scope_id": item.scope_id, "metadata": item.metadata_json} for item in events]
