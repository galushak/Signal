import secrets
from html import escape
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth
from .audit import record
from .authorization import BUILDING, DISTRICT, PLAYER, ZONE, allowed, require, visible_building_ids, visible_player_ids
from .database import get_db
from .models import AuditEvent, Building, Content, ContentAssignment, ContentTemplate, ContentVersion, Layout, LayoutVersion, MediaAsset, MediaAssetTag, MediaFolder, PermissionGrant, Player, PlayerCommand, PlayerEnrollment, Tag, User, Zone
from .player_protocol import MANIFEST_SCHEMA, build_manifest, media_is_allowed
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
    layout_id: str | None = None


class DeviceEnrollmentInput(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    device_identifier: str = Field(min_length=8, max_length=255)
    software_version: str = Field(default="unknown", max_length=80)
    platform_metadata: dict | None = None


class EnrollmentValidationInput(BaseModel):
    code: str = Field(min_length=4, max_length=32)


class HeartbeatInput(BaseModel):
    software_version: str = Field(default="unknown", max_length=80)
    applied_state_revision: str | None = Field(default=None, max_length=128)
    renderer_status: str = Field(default="unknown", max_length=32)
    cache_state: str = Field(default="unknown", max_length=32)
    resolution: str | None = Field(default=None, max_length=32)
    current_content: str | None = Field(default=None, max_length=160)
    uptime_seconds: int | None = Field(default=None, ge=0)
    disk_usage: dict | None = None
    network_state: dict | None = None
    temperature: str | float | None = None


class CommandInput(BaseModel):
    command: str


class CommandResultInput(BaseModel):
    status: str = Field(pattern="^(completed|failed|unsupported)$")
    result: dict | None = None


class LayoutInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    enabled: bool = True
    locked: bool = False
    note: str | None = Field(default=None, max_length=500)


class ZoneInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    x: int = Field(default=0, ge=0, le=1919)
    y: int = Field(default=0, ge=0, le=1079)
    width: int = Field(default=1920, ge=1, le=1920)
    height: int = Field(default=1080, ge=1, le=1080)
    z_index: int = Field(default=0, ge=0, le=99)
    background: str | None = Field(default=None, max_length=64)
    border: dict | None = None
    padding: int = Field(default=0, ge=0, le=200)
    enabled: bool = True
    locked: bool = False


class ContentInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    content_type: str = "design"
    scope_type: str = DISTRICT
    scope_id: str | None = None
    design_document: dict = Field(default_factory=lambda: {"schema": "signal.design/v1", "canvas": {"width": 1920, "height": 1080}, "elements": []})
    note: str | None = Field(default=None, max_length=500)


class DraftInput(BaseModel):
    design_document: dict
    note: str | None = Field(default=None, max_length=500)


class AssignmentInput(BaseModel):
    destination_type: str
    destination_id: str
    enabled: bool = True
    priority: int = Field(default=1, ge=1, le=3)
    duration_seconds: int | None = Field(default=None, ge=1, le=3600)
    transition: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    weekdays: list[int] | None = None
    daily_start: str | None = None
    daily_end: str | None = None


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    design_document: dict
    enabled: bool = True


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
    last_seen = auth.utc_datetime(player.last_seen_at) if player.last_seen_at else None
    state = "waiting_for_enrollment" if player.enrollment_status == "pending" else ("not_enrolled" if player.enrollment_status == "not_enrolled" else ("never_connected" if not last_seen else ("online" if datetime.now(UTC) - last_seen <= timedelta(seconds=75) else "offline")))
    runtime = player.runtime_data or {}
    return {"id": player.id, "name": player.name, "building_id": player.building_id, "building_name": player.building.name, "description": player.description, "enabled": player.enabled, "layout_id": player.layout_id, "enrollment_status": player.enrollment_status, "last_seen_at": player.last_seen_at, "software_version": player.software_version, "resolution": player.resolution, "health_state": state, "cache_state": player.cache_state, "desired_state_revision": player.desired_state_revision, "applied_state_revision": player.applied_state_revision, "runtime": runtime, "created_at": player.created_at, "updated_at": player.updated_at}


def agent_player(request: Request, db: Session) -> Player:
    """Authenticate a device token without involving human JWT sessions."""
    player_id = request.headers.get("x-signal-player-id")
    secret = request.headers.get("x-signal-player-secret")
    player = db.get(Player, player_id) if player_id else None
    if not player or not player.enabled or not player.device_secret_hash or not secret or not auth.verify_password(secret, player.device_secret_hash):
        raise HTTPException(status_code=401, detail="A valid Signal Player credential is required.")
    return player


def media_data(asset: MediaAsset, db: Session) -> dict:
    tag_names = db.scalars(select(Tag.name).join(MediaAssetTag, Tag.id == MediaAssetTag.tag_id).where(MediaAssetTag.asset_id == asset.id)).all()
    return {"id": asset.id, "display_name": asset.display_name, "original_filename": asset.original_filename, "media_type": asset.media_type, "mime_type": asset.mime_type, "file_size": asset.file_size, "processing_state": asset.processing_state, "processing_error": asset.processing_error, "width": asset.width, "height": asset.height, "duration_seconds": asset.duration_seconds, "scope_type": asset.scope_type, "scope_id": asset.scope_id, "folder_id": asset.folder_id, "uploaded_by_id": asset.uploaded_by_id, "created_at": asset.created_at, "trashed_at": asset.trashed_at, "tags": tag_names, "file_url": f"/api/v1/media/{asset.id}/file", "thumbnail_url": f"/api/v1/media/{asset.id}/thumbnail" if asset.thumbnail_path else None}


def scope_valid(scope_type: str, scope_id: str | None, db: Session) -> None:
    if scope_type not in {DISTRICT, BUILDING, PLAYER, ZONE}:
        raise HTTPException(status_code=422, detail="Choose District, Building, Player, or Zone for access.")
    if scope_type == DISTRICT and scope_id is not None:
        raise HTTPException(status_code=422, detail="District access does not need a specific item.")
    if scope_type == BUILDING and (not scope_id or not db.get(Building, scope_id)):
        raise HTTPException(status_code=422, detail="Choose a valid building.")
    if scope_type == PLAYER and (not scope_id or not db.get(Player, scope_id)):
        raise HTTPException(status_code=422, detail="Choose a valid player.")
    if scope_type == ZONE and (not scope_id or not db.get(Zone, scope_id)):
        raise HTTPException(status_code=422, detail="Choose a valid zone.")


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
    if payload.layout_id and not db.get(Layout, payload.layout_id): raise HTTPException(status_code=422, detail="Choose a valid layout.")
    player = Player(name=payload.name.strip(), building_id=payload.building_id, description=payload.description, enabled=payload.enabled, resolution=payload.resolution, layout_id=payload.layout_id)
    db.add(player); db.flush()
    record(db, actor=user, action="player.created", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit(); db.refresh(player); return player_data(player)


@router.patch("/players/{player_id}")
def update_player(player_id: str, payload: PlayerInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "manage_players", PLAYER, player.id, db); scope_valid(BUILDING, payload.building_id, db)
    if payload.layout_id and not db.get(Layout, payload.layout_id): raise HTTPException(status_code=422, detail="Choose a valid layout.")
    player.name, player.building_id, player.description, player.enabled, player.resolution, player.layout_id = payload.name.strip(), payload.building_id, payload.description, payload.enabled, payload.resolution, payload.layout_id
    record(db, actor=user, action="player.updated", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit(); db.refresh(player); return player_data(player)


ENROLLMENT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normal_enrollment_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


def new_enrollment_code() -> str:
    raw = "".join(secrets.choice(ENROLLMENT_ALPHABET) for _ in range(6))
    return f"{raw[:3]}-{raw[3:]}"


def enrollment_state(enrollment: PlayerEnrollment) -> str:
    if enrollment.claimed_at:
        return "used"
    if enrollment.cancelled_at:
        return "cancelled"
    if auth.utc_datetime(enrollment.expires_at) <= datetime.now(UTC):
        return "expired"
    return "valid"


def enrollment_code_state(code: str, db: Session) -> tuple[PlayerEnrollment | None, str]:
    """Find a hashed code without exposing durable credentials."""
    normalized = normal_enrollment_code(code)
    for enrollment in db.scalars(select(PlayerEnrollment).order_by(PlayerEnrollment.created_at.desc())).all():
        if auth.verify_password(normalized, enrollment.code_hash):
            return enrollment, enrollment_state(enrollment)
    return None, "invalid"


def enrollment_data(enrollment: PlayerEnrollment, *, include_code: bool) -> dict:
    data = {"id": enrollment.id, "status": enrollment_state(enrollment), "expires_at": enrollment.expires_at, "player_id": enrollment.player_id}
    if include_code and enrollment.display_code and not enrollment.claimed_at and not enrollment.cancelled_at:
        data["code"] = enrollment.display_code
    return data


def issue_server_enrollment(player: Player, request: Request, user: User, db: Session, *, action: str) -> PlayerEnrollment:
    now = datetime.now(UTC)
    for pending in db.scalars(select(PlayerEnrollment).where(PlayerEnrollment.player_id == player.id, PlayerEnrollment.claimed_at.is_(None), PlayerEnrollment.cancelled_at.is_(None))).all():
        pending.cancelled_at, pending.display_code = now, None
    code = new_enrollment_code()
    enrollment = PlayerEnrollment(player_id=player.id, created_by_id=user.id, code_hash=auth.hash_password(code), display_code=code, expires_at=now + timedelta(minutes=settings.enrollment_code_ttl_minutes))
    player.enrollment_status = "pending"
    db.add(enrollment); db.flush()
    record(db, actor=user, action=action, resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request), metadata={"enrollment_id": enrollment.id})
    return enrollment


def can_manage_any_display(user: User, db: Session) -> bool:
    return user.super_admin or bool(db.scalar(select(PermissionGrant.id).where(PermissionGrant.user_id == user.id, PermissionGrant.capability == "manage_players")))


@router.get("/player-enrollments/options")
def player_enrollment_options(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not can_manage_any_display(user, db):
        raise HTTPException(status_code=403, detail="You don't have permission to enroll displays.")
    buildings = [building_data(item) for item in db.scalars(select(Building).where(Building.enabled.is_(True)).order_by(Building.name)) if allowed(user, "manage_players", BUILDING, item.id, db)]
    # Layouts are district-managed in the current permission model. Do not leak
    # layout names to a building-only administrator.
    layouts = [layout_data(item) for item in db.scalars(select(Layout).where(Layout.enabled.is_(True), Layout.trashed_at.is_(None)).order_by(Layout.name))] if allowed(user, "manage_layouts", DISTRICT, None, db) else []
    return {"buildings": buildings, "layouts": layouts}


@router.post("/player-enrollments/validate")
def validate_player_enrollment(payload: EnrollmentValidationInput, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not can_manage_any_display(user, db):
        raise HTTPException(status_code=403, detail="You don't have permission to enroll displays.")
    _, state = enrollment_code_state(payload.code, db)
    return {"status": state}

@router.post("/players/prepare-enrollment", status_code=201)
def prepare_player_enrollment(payload: PlayerInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    scope_valid(BUILDING, payload.building_id, db)
    require(user, "manage_players", BUILDING, payload.building_id, db)
    if payload.layout_id and not db.get(Layout, payload.layout_id): raise HTTPException(status_code=422, detail="Choose a valid layout.")
    player = Player(name=payload.name.strip(), building_id=payload.building_id, description=payload.description, enabled=payload.enabled, resolution=payload.resolution, layout_id=payload.layout_id, enrollment_status="pending", health_state="waiting_for_enrollment")
    db.add(player); db.flush()
    enrollment = issue_server_enrollment(player, request, user, db, action="player.enrollment_prepared")
    db.commit(); db.refresh(player)
    return {"player": player_data(player), "enrollment": enrollment_data(enrollment, include_code=True)}


@router.post("/players/{player_id}/enrollment")
@router.post("/players/{player_id}/enrollment/regenerate")
def regenerate_player_enrollment(player_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "manage_players", PLAYER, player.id, db)
    if player.device_secret_hash: raise HTTPException(status_code=409, detail="Reset this enrolled device before generating a new enrollment code.")
    enrollment = issue_server_enrollment(player, request, user, db, action="player.enrollment_code_regenerated")
    db.commit()
    return {"player": player_data(player), "enrollment": enrollment_data(enrollment, include_code=True)}


@router.delete("/players/{player_id}/enrollment", status_code=204)
def cancel_player_enrollment(player_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "manage_players", PLAYER, player.id, db)
    now = datetime.now(UTC)
    for pending in db.scalars(select(PlayerEnrollment).where(PlayerEnrollment.player_id == player.id, PlayerEnrollment.claimed_at.is_(None), PlayerEnrollment.cancelled_at.is_(None))).all():
        pending.cancelled_at, pending.display_code = now, None
    player.enrollment_status = "not_enrolled"
    record(db, actor=user, action="player.enrollment_cancelled", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request))
    db.commit()


@router.post("/device/enroll", status_code=201)
def device_enroll(payload: DeviceEnrollmentInput, request: Request, db: Session = Depends(get_db)):
    auth.check_device_enrollment_rate_limit(f"{auth.client_ip(request) or 'unknown'}:{normal_enrollment_code(payload.code)}")
    enrollment, state = enrollment_code_state(payload.code, db)
    if state == "expired": raise HTTPException(status_code=410, detail="That enrollment code has expired. Generate a new code in Signal and enter it here.")
    if state == "used": raise HTTPException(status_code=409, detail="That enrollment code has already been used.")
    if state != "valid" or not enrollment or not enrollment.player_id:
        raise HTTPException(status_code=404, detail="That enrollment code is not valid.")
    player = db.get(Player, enrollment.player_id)
    if not player or not player.enabled:
        raise HTTPException(status_code=409, detail="This prepared display is no longer available.")
    secret = secrets.token_urlsafe(32)
    try:
        enrollment.device_identifier = payload.device_identifier
        enrollment.claimed_at = datetime.now(UTC)
        enrollment.display_code = None
        player.device_identifier = payload.device_identifier
        player.device_secret_hash = auth.hash_password(secret)
        player.enrollment_status = "enrolled"
        player.software_version = payload.software_version
        player.network_info = {"last_reported_ip": auth.client_ip(request), "platform": payload.platform_metadata or {}}
        record(db, actor=None, action="player.device_enrolled", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request), metadata={"enrollment_id": enrollment.id, "device_identifier": payload.device_identifier})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"player_id": player.id, "device_secret": secret, "server_time": datetime.now(UTC)}


@router.post("/player-agent/enrollment/start", deprecated=True)
def retired_player_generated_enrollment():
    raise HTTPException(status_code=410, detail="Player-generated enrollment codes were retired. Generate a code in Signal and enter it on the player.")


@router.get("/player-agent/enrollment/{code}", deprecated=True)
def retired_player_generated_status(code: str):
    raise HTTPException(status_code=410, detail="Player-generated enrollment codes were retired.")


@router.post("/players/enroll", deprecated=True)
def retired_admin_claim():
    raise HTTPException(status_code=410, detail="Prepare the display first, then enter the server-generated code on the player.")


@router.post("/players/{player_id}/commands", status_code=201)
def queue_player_command(player_id: str, payload: CommandInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "restart_players", PLAYER, player.id, db)
    if payload.command not in {"force_sync", "restart_renderer", "restart_player", "clear_cache", "screenshot"}:
        raise HTTPException(status_code=422, detail="Unsupported player command.")
    command = PlayerCommand(player_id=player.id, command=payload.command, requested_by_id=user.id)
    db.add(command); db.flush(); record(db, actor=user, action="player.command_queued", resource_type="player", resource_id=player.id, resource_name=player.name, scope_type=PLAYER, scope_id=player.id, source_ip=auth.client_ip(request), metadata={"command": payload.command}); db.commit()
    return {"id": command.id, "status": command.status}


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
    scope_id = scope_id or None
    folder_id = folder_id or None
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


@router.post("/player-agent/heartbeat")
def player_heartbeat(payload: HeartbeatInput, request: Request, db: Session = Depends(get_db)):
    player = agent_player(request, db)
    player.last_seen_at = datetime.now(UTC)
    player.software_version = payload.software_version
    player.applied_state_revision = payload.applied_state_revision
    player.resolution = payload.resolution or player.resolution
    player.health_state = "online"
    player.cache_state = payload.cache_state
    player.network_info = payload.network_state
    player.runtime_data = {"renderer_status": payload.renderer_status, "current_content": payload.current_content, "uptime_seconds": payload.uptime_seconds, "disk_usage": payload.disk_usage, "temperature": payload.temperature}
    manifest = build_manifest(player, db)
    player.desired_state_revision = manifest["revision"]
    db.commit()
    return {"ok": True, "desired_state_revision": manifest["revision"], "poll_after_seconds": 15}


@router.get("/player-agent/manifest")
def player_manifest(request: Request, db: Session = Depends(get_db)):
    player = agent_player(request, db)
    manifest = build_manifest(player, db)
    player.desired_state_revision = manifest["revision"]
    db.commit()
    etag = f'"{manifest["revision"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(manifest, headers={"ETag": etag, "Cache-Control": "no-store"})


@router.get("/player-agent/media/{asset_id}")
def player_media(asset_id: str, request: Request, db: Session = Depends(get_db)):
    player = agent_player(request, db)
    asset = media_is_allowed(asset_id, player, db)
    if not asset:
        raise HTTPException(status_code=404, detail="This media item is not in the player's desired state.")
    path = settings.media_root / (asset.processed_path or asset.original_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The media file is not available.")
    return FileResponse(path, media_type=asset.mime_type, filename=asset.original_filename)


@router.get("/player-agent/commands")
def poll_player_commands(request: Request, db: Session = Depends(get_db)):
    player = agent_player(request, db)
    queued = db.scalars(select(PlayerCommand).where(PlayerCommand.player_id == player.id, PlayerCommand.status == "queued").order_by(PlayerCommand.created_at)).all()
    for command in queued: command.status = "delivered"
    db.commit()
    return [{"id": command.id, "command": command.command} for command in queued]


@router.post("/player-agent/commands/{command_id}/result")
def player_command_result(command_id: str, payload: CommandResultInput, request: Request, db: Session = Depends(get_db)):
    player = agent_player(request, db)
    command = db.get(PlayerCommand, command_id)
    if not command or command.player_id != player.id:
        raise HTTPException(status_code=404, detail="Command not found.")
    command.status, command.result, command.completed_at = payload.status, payload.result, datetime.now(UTC)
    db.commit()
    return {"ok": True}


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


def zone_data(zone: Zone) -> dict:
    return {"id": zone.id, "layout_id": zone.layout_id, "name": zone.name, "x": zone.x, "y": zone.y, "width": zone.width, "height": zone.height, "z_index": zone.z_index, "background": zone.background, "border": zone.border, "padding": zone.padding, "enabled": zone.enabled, "locked": zone.locked}


def layout_definition(layout: Layout) -> dict:
    return {"schema": "signal.layout/v1", "canvas": {"width": layout.logical_width, "height": layout.logical_height}, "locked": layout.locked, "zones": [zone_data(zone) for zone in sorted(layout.zones, key=lambda item: (item.z_index, item.name))]}


def layout_data(layout: Layout) -> dict:
    return {"id": layout.id, "name": layout.name, "description": layout.description, "logical_width": layout.logical_width, "logical_height": layout.logical_height, "enabled": layout.enabled, "locked": layout.locked, "created_at": layout.created_at, "updated_at": layout.updated_at, "zones": [zone_data(zone) for zone in sorted(layout.zones, key=lambda item: (item.z_index, item.name))]}


def content_data(item: Content, db: Session) -> dict:
    versions = db.scalars(select(ContentVersion).where(ContentVersion.content_id == item.id).order_by(ContentVersion.revision.desc())).all()
    published = next((version for version in versions if version.state == "published"), None)
    draft = next((version for version in versions if version.state == "draft"), None)
    return {"id": item.id, "name": item.name, "content_type": item.content_type, "scope_type": item.scope_type, "scope_id": item.scope_id, "created_by_id": item.created_by_id, "created_at": item.created_at, "updated_at": item.updated_at, "trashed_at": item.trashed_at, "published_version": version_data(published) if published else None, "draft_version": version_data(draft) if draft else None}


def version_data(version: ContentVersion | None) -> dict | None:
    if not version: return None
    return {"id": version.id, "revision": version.revision, "state": version.state, "design_document": version.design_document, "note": version.note, "created_by_id": version.created_by_id, "created_at": version.created_at, "published_at": version.published_at}


def assignment_data(item: ContentAssignment) -> dict:
    return {"id": item.id, "content_id": item.content_id, "destination_type": item.destination_type, "destination_id": item.destination_id, "enabled": item.enabled, "priority": item.priority, "duration_seconds": item.duration_seconds, "transition": item.transition, "starts_at": item.starts_at, "ends_at": item.ends_at, "weekdays": item.weekdays, "daily_start": item.daily_start, "daily_end": item.daily_end}


@router.get("/layouts")
def list_layouts(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db)
    return [layout_data(item) for item in db.scalars(select(Layout).where(Layout.trashed_at.is_(None)).order_by(Layout.name))]


@router.post("/layouts", status_code=201)
def create_layout(payload: LayoutInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db)
    if db.scalar(select(Layout).where(Layout.name == payload.name.strip())): raise HTTPException(status_code=409, detail="A layout with that name already exists.")
    layout = Layout(name=payload.name.strip(), description=payload.description, enabled=payload.enabled, locked=payload.locked, created_by_id=user.id)
    db.add(layout); db.flush(); db.add(LayoutVersion(layout_id=layout.id, revision=1, definition=layout_definition(layout), note=payload.note, created_by_id=user.id))
    record(db, actor=user, action="layout.created", resource_type="layout", resource_id=layout.id, resource_name=layout.name, source_ip=auth.client_ip(request)); db.commit(); db.refresh(layout)
    return layout_data(layout)


@router.patch("/layouts/{layout_id}")
def update_layout(layout_id: str, payload: LayoutInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db); layout = db.get(Layout, layout_id)
    if not layout or layout.trashed_at: raise HTTPException(status_code=404, detail="Layout not found.")
    layout.name, layout.description, layout.enabled, layout.locked = payload.name.strip(), payload.description, payload.enabled, payload.locked
    revision = (db.scalar(select(func.max(LayoutVersion.revision)).where(LayoutVersion.layout_id == layout.id)) or 0) + 1
    db.add(LayoutVersion(layout_id=layout.id, revision=revision, definition=layout_definition(layout), note=payload.note, created_by_id=user.id)); record(db, actor=user, action="layout.updated", resource_type="layout", resource_id=layout.id, resource_name=layout.name, source_ip=auth.client_ip(request)); db.commit(); db.refresh(layout); return layout_data(layout)


@router.get("/layouts/{layout_id}/versions")
def list_layout_versions(layout_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db); return [{"id": item.id, "revision": item.revision, "definition": item.definition, "note": item.note, "created_at": item.created_at} for item in db.scalars(select(LayoutVersion).where(LayoutVersion.layout_id == layout_id).order_by(LayoutVersion.revision.desc()))]


@router.post("/layouts/{layout_id}/restore/{revision}")
def restore_layout(layout_id: str, revision: int, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db); layout = db.get(Layout, layout_id); prior = db.scalar(select(LayoutVersion).where(LayoutVersion.layout_id == layout_id, LayoutVersion.revision == revision))
    if not layout or not prior: raise HTTPException(status_code=404, detail="Layout revision not found.")
    for zone in list(layout.zones): db.delete(zone)
    for source in prior.definition.get("zones", []): db.add(Zone(layout_id=layout.id, name=source["name"], x=source["x"], y=source["y"], width=source["width"], height=source["height"], z_index=source.get("z_index", 0), background=source.get("background"), border=source.get("border"), padding=source.get("padding", 0), enabled=source.get("enabled", True), locked=source.get("locked", False)))
    db.flush(); next_revision = (db.scalar(select(func.max(LayoutVersion.revision)).where(LayoutVersion.layout_id == layout.id)) or 0) + 1; db.add(LayoutVersion(layout_id=layout.id, revision=next_revision, definition=layout_definition(layout), note=f"Restored revision {revision}", created_by_id=user.id)); record(db, actor=user, action="layout.restored", resource_type="layout", resource_id=layout.id, resource_name=layout.name, source_ip=auth.client_ip(request), metadata={"from_revision": revision}); db.commit(); return layout_data(layout)


@router.post("/layouts/{layout_id}/zones", status_code=201)
def create_zone(layout_id: str, payload: ZoneInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_layouts", DISTRICT, None, db); layout = db.get(Layout, layout_id)
    if not layout or layout.trashed_at: raise HTTPException(status_code=404, detail="Layout not found.")
    if payload.x + payload.width > layout.logical_width or payload.y + payload.height > layout.logical_height: raise HTTPException(status_code=422, detail="Zone must fit within the 1920 × 1080 layout.")
    zone = Zone(layout_id=layout.id, **payload.model_dump()); db.add(zone); db.flush(); record(db, actor=user, action="zone.created", resource_type="zone", resource_id=zone.id, resource_name=zone.name, scope_type=ZONE, scope_id=zone.id, source_ip=auth.client_ip(request)); db.commit(); return zone_data(zone)


@router.patch("/zones/{zone_id}")
def update_zone(zone_id: str, payload: ZoneInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    zone = db.get(Zone, zone_id)
    if not zone: raise HTTPException(status_code=404, detail="Zone not found.")
    require(user, "manage_layouts", DISTRICT, None, db)
    if payload.x + payload.width > 1920 or payload.y + payload.height > 1080: raise HTTPException(status_code=422, detail="Zone must fit within the layout.")
    for key, value in payload.model_dump().items(): setattr(zone, key, value)
    record(db, actor=user, action="zone.updated", resource_type="zone", resource_id=zone.id, resource_name=zone.name, scope_type=ZONE, scope_id=zone.id, source_ip=auth.client_ip(request)); db.commit(); return zone_data(zone)


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    zone = db.get(Zone, zone_id)
    if not zone: raise HTTPException(status_code=404, detail="Zone not found.")
    require(user, "manage_layouts", DISTRICT, None, db); assigned = db.scalar(select(func.count()).select_from(ContentAssignment).where(ContentAssignment.destination_type == ZONE, ContentAssignment.destination_id == zone.id)); db.delete(zone); record(db, actor=user, action="zone.deleted", resource_type="zone", resource_id=zone_id, resource_name=zone.name, scope_type=ZONE, scope_id=zone_id, source_ip=auth.client_ip(request), metadata={"assignment_count": assigned}); db.commit(); return {"ok": True, "affected_assignments": assigned}


def valid_design(document: dict) -> None:
    if document.get("schema") != "signal.design/v1" or not isinstance(document.get("elements"), list): raise HTTPException(status_code=422, detail="Use a Signal design document with an elements list.")
    ids = [element.get("id") for element in document["elements"]]
    if any(not isinstance(element_id, str) or not element_id for element_id in ids) or len(ids) != len(set(ids)): raise HTTPException(status_code=422, detail="Every design element needs a stable unique ID.")


def content_for_user(content_id: str, capability: str, user: User, db: Session) -> Content:
    item = db.get(Content, content_id)
    if not item or item.trashed_at: raise HTTPException(status_code=404, detail="Content not found.")
    require(user, capability, item.scope_type, item.scope_id, db); return item


@router.get("/content")
def list_content(include_trashed: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    query = select(Content).order_by(Content.updated_at.desc())
    if not include_trashed: query = query.where(Content.trashed_at.is_(None))
    return [content_data(item, db) for item in db.scalars(query) if allowed(user, "view", item.scope_type, item.scope_id, db)]


def design_thumbnail_svg(document: dict) -> str:
    """A safe, lightweight thumbnail for the structured design — never a new
    flattened Content object. The canonical editable JSON remains unchanged.
    """
    canvas = document.get("canvas") or {}
    background = escape(str(canvas.get("background") or "#172d43"), quote=True)
    elements = document.get("elements") or []
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="{background}"/>']
    for element in elements[:24]:
        x, y = int(element.get("x", 0)), int(element.get("y", 0))
        width, height = int(element.get("width", 200)), int(element.get("height", 80))
        style = element.get("style") or {}
        if element.get("type") in {"shape", "image", "video", "pdf", "website"}:
            parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{int(style.get("cornerRadius", 0))}" fill="{escape(str(style.get("fill", "#54657a")), quote=True)}"/>')
        text = escape(str(element.get("text") or ""))[:140]
        if text:
            fill = escape(str(style.get("fill", "#ffffff")), quote=True)
            size = min(160, max(12, int(style.get("fontSize", 44))))
            anchor = {"center": "middle", "right": "end"}.get(style.get("textAlign"), "start")
            tx = x + (width / 2 if anchor == "middle" else width if anchor == "end" else 0)
            parts.append(f'<text x="{tx}" y="{y + min(height, size)}" fill="{fill}" font-family="Arial, sans-serif" font-size="{size}" text-anchor="{anchor}">{text}</text>')
    return "".join(parts) + "</svg>"


@router.get("/content/{content_id}/thumbnail.svg")
def content_thumbnail(content_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    item = content_for_user(content_id, "view", user, db)
    versions = db.scalars(select(ContentVersion).where(ContentVersion.content_id == item.id).order_by(ContentVersion.revision.desc())).all()
    version = next((candidate for candidate in versions if candidate.state in {"draft", "published"}), None)
    if not version:
        raise HTTPException(status_code=404, detail="A design thumbnail is not available.")
    return Response(content=design_thumbnail_svg(version.design_document), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/library")
def unified_library(kind: str = "all", search: str | None = None, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if kind not in {"all", "design", "image", "video", "pdf"}:
        raise HTTPException(status_code=422, detail="Choose All, Designs, Images, Videos, or PDFs.")
    needle = (search or "").strip().lower()
    items = []
    if kind in {"all", "design"}:
        for content in db.scalars(select(Content).where(Content.trashed_at.is_(None)).order_by(Content.updated_at.desc())):
            if not allowed(user, "view", content.scope_type, content.scope_id, db) or needle and needle not in content.name.lower():
                continue
            data = content_data(content, db)
            items.append({"id": content.id, "kind": "design", "name": content.name, "status": "Published" if data["published_version"] else "Draft", "updated_at": content.updated_at, "thumbnail_url": f"/api/v1/content/{content.id}/thumbnail.svg", "scope_type": content.scope_type, "scope_id": content.scope_id})
    if kind in {"all", "image", "video", "pdf"}:
        for asset in db.scalars(select(MediaAsset).where(MediaAsset.trashed_at.is_(None)).order_by(MediaAsset.created_at.desc())):
            tags = db.scalars(select(Tag.name).join(MediaAssetTag, Tag.id == MediaAssetTag.tag_id).where(MediaAssetTag.asset_id == asset.id)).all()
            if not allowed(user, "view", asset.scope_type, asset.scope_id, db) or kind != "all" and asset.media_type != kind or needle and needle not in asset.display_name.lower() and needle not in tags:
                continue
            items.append({"id": asset.id, "kind": asset.media_type, "name": asset.display_name, "status": asset.processing_state, "updated_at": asset.updated_at, "thumbnail_url": f"/api/v1/media/{asset.id}/thumbnail" if asset.thumbnail_path else None, "scope_type": asset.scope_type, "scope_id": asset.scope_id, "tags": tags})
    return sorted(items, key=lambda item: item["updated_at"] or datetime.min.replace(tzinfo=UTC), reverse=True)


@router.post("/content", status_code=201)
def create_content(payload: ContentInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    scope_valid(payload.scope_type, payload.scope_id, db); require(user, "create_content", payload.scope_type, payload.scope_id, db); valid_design(payload.design_document)
    item = Content(name=payload.name.strip(), content_type=payload.content_type, scope_type=payload.scope_type, scope_id=payload.scope_id, created_by_id=user.id); db.add(item); db.flush(); version = ContentVersion(content_id=item.id, revision=1, state="draft", design_document=payload.design_document, note=payload.note, created_by_id=user.id); db.add(version); record(db, actor=user, action="content.created", resource_type="content", resource_id=item.id, resource_name=item.name, scope_type=item.scope_type, scope_id=item.scope_id, source_ip=auth.client_ip(request)); db.commit(); return content_data(item, db)


@router.get("/content/{content_id}/versions")
def list_content_versions(content_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    content_for_user(content_id, "view", user, db); return [version_data(item) for item in db.scalars(select(ContentVersion).where(ContentVersion.content_id == content_id).order_by(ContentVersion.revision.desc()))]


@router.post("/content/{content_id}/draft")
def save_draft(content_id: str, payload: DraftInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    item = content_for_user(content_id, "edit_content", user, db); valid_design(payload.design_document); existing = db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.state == "draft"))
    if existing: existing.design_document, existing.note = payload.design_document, payload.note; version = existing
    else:
        revision = (db.scalar(select(func.max(ContentVersion.revision)).where(ContentVersion.content_id == item.id)) or 0) + 1; version = ContentVersion(content_id=item.id, revision=revision, state="draft", design_document=payload.design_document, note=payload.note, created_by_id=user.id); db.add(version)
    record(db, actor=user, action="content.draft_saved", resource_type="content", resource_id=item.id, resource_name=item.name, scope_type=item.scope_type, scope_id=item.scope_id, source_ip=auth.client_ip(request)); db.commit(); return version_data(version)


@router.post("/content/{content_id}/publish")
def publish_content(content_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    item = content_for_user(content_id, "publish", user, db); draft = db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.state == "draft"))
    if not draft: raise HTTPException(status_code=409, detail="There are no draft changes to publish.")
    for prior in db.scalars(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.state == "published")): prior.state = "superseded"
    draft.state, draft.published_at = "published", datetime.now(UTC); record(db, actor=user, action="content.published", resource_type="content", resource_id=item.id, resource_name=item.name, scope_type=item.scope_type, scope_id=item.scope_id, source_ip=auth.client_ip(request), metadata={"revision": draft.revision}); db.commit(); return version_data(draft)


@router.post("/content/{content_id}/restore/{revision}")
def restore_content(content_id: str, revision: int, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    item = content_for_user(content_id, "restore_versions", user, db); prior = db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.revision == revision))
    if not prior: raise HTTPException(status_code=404, detail="Content revision not found.")
    if db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.state == "draft")): raise HTTPException(status_code=409, detail="Discard or save the current draft before restoring a revision.")
    next_revision = (db.scalar(select(func.max(ContentVersion.revision)).where(ContentVersion.content_id == item.id)) or 0) + 1; version = ContentVersion(content_id=item.id, revision=next_revision, state="draft", design_document=prior.design_document, note=f"Restored from revision {revision}", created_by_id=user.id); db.add(version); record(db, actor=user, action="content.restored", resource_type="content", resource_id=item.id, resource_name=item.name, scope_type=item.scope_type, scope_id=item.scope_id, source_ip=auth.client_ip(request), metadata={"from_revision": revision}); db.commit(); return version_data(version)


@router.post("/content/{content_id}/assignments", status_code=201)
def create_assignment(content_id: str, payload: AssignmentInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    item = content_for_user(content_id, "schedule", user, db)
    if payload.destination_type not in {PLAYER, ZONE}: raise HTTPException(status_code=422, detail="Choose a player or zone destination.")
    scope_valid(payload.destination_type, payload.destination_id, db); require(user, "schedule", payload.destination_type, payload.destination_id, db)
    if payload.ends_at and payload.starts_at and payload.ends_at <= payload.starts_at: raise HTTPException(status_code=422, detail="The expiration must be after the start time.")
    if payload.transition not in {None, "none", "fade", "slide"}: raise HTTPException(status_code=422, detail="Choose None, Fade, or Slide for the transition.")
    if payload.weekdays and any(day not in range(7) for day in payload.weekdays): raise HTTPException(status_code=422, detail="Weekdays must be numbers from 0 (Monday) to 6 (Sunday).")
    assignment = ContentAssignment(content_id=item.id, created_by_id=user.id, **payload.model_dump()); db.add(assignment); db.flush(); record(db, actor=user, action="assignment.created", resource_type="assignment", resource_id=assignment.id, resource_name=item.name, scope_type=payload.destination_type, scope_id=payload.destination_id, source_ip=auth.client_ip(request)); db.commit(); return assignment_data(assignment)


@router.get("/content/{content_id}/assignments")
def list_assignments(content_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    content_for_user(content_id, "view", user, db)
    return [assignment_data(item) for item in db.scalars(select(ContentAssignment).where(ContentAssignment.content_id == content_id)) if allowed(user, "view", item.destination_type, item.destination_id, db)]


@router.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: AssignmentInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    assignment = db.get(ContentAssignment, assignment_id)
    if not assignment: raise HTTPException(status_code=404, detail="Assignment not found.")
    content_for_user(assignment.content_id, "schedule", user, db); scope_valid(payload.destination_type, payload.destination_id, db); require(user, "schedule", payload.destination_type, payload.destination_id, db)
    if payload.ends_at and payload.starts_at and payload.ends_at <= payload.starts_at: raise HTTPException(status_code=422, detail="The expiration must be after the start time.")
    if payload.transition not in {None, "none", "fade", "slide"}: raise HTTPException(status_code=422, detail="Choose None, Fade, or Slide for the transition.")
    for key, value in payload.model_dump().items(): setattr(assignment, key, value)
    record(db, actor=user, action="assignment.updated", resource_type="assignment", resource_id=assignment.id, scope_type=assignment.destination_type, scope_id=assignment.destination_id, source_ip=auth.client_ip(request)); db.commit(); return assignment_data(assignment)


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: str, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    assignment = db.get(ContentAssignment, assignment_id)
    if not assignment: raise HTTPException(status_code=404, detail="Assignment not found.")
    content_for_user(assignment.content_id, "schedule", user, db); require(user, "schedule", assignment.destination_type, assignment.destination_id, db); db.delete(assignment)
    record(db, actor=user, action="assignment.removed", resource_type="assignment", resource_id=assignment_id, scope_type=assignment.destination_type, scope_id=assignment.destination_id, source_ip=auth.client_ip(request)); db.commit(); return {"ok": True}


@router.get("/templates")
def list_templates(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.super_admin and not db.scalars(select(PermissionGrant).where(PermissionGrant.user_id == user.id, PermissionGrant.capability == "create_content")).first(): raise HTTPException(status_code=403, detail="You don't have permission to create content.")
    return [{"id": item.id, "name": item.name, "design_document": item.design_document, "enabled": item.enabled, "created_at": item.created_at} for item in db.scalars(select(ContentTemplate).where(ContentTemplate.trashed_at.is_(None), ContentTemplate.enabled.is_(True)).order_by(ContentTemplate.name))]


@router.get("/destinations")
def list_destinations(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    players = [player_data(item) for item in db.scalars(select(Player).order_by(Player.name)) if allowed(user, "view", PLAYER, item.id, db)]
    zones = []
    for item in db.scalars(select(Zone).order_by(Zone.name)):
        if allowed(user, "view", ZONE, item.id, db): zones.append({**zone_data(item), "layout_name": item.layout.name})
    return {"players": players, "zones": zones}


@router.post("/templates", status_code=201)
def create_template(payload: TemplateInput, request: Request, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    require(user, "manage_templates", DISTRICT, None, db); valid_design(payload.design_document)
    if db.scalar(select(ContentTemplate).where(ContentTemplate.name == payload.name.strip())): raise HTTPException(status_code=409, detail="A template with that name already exists.")
    template = ContentTemplate(name=payload.name.strip(), design_document=payload.design_document, enabled=payload.enabled, created_by_id=user.id); db.add(template); db.flush(); record(db, actor=user, action="template.created", resource_type="template", resource_id=template.id, resource_name=template.name, source_ip=auth.client_ip(request)); db.commit(); return {"id": template.id, "name": template.name}


def eligible(assignment: ContentAssignment, now: datetime) -> bool:
    if not assignment.enabled or (assignment.starts_at and assignment.starts_at > now) or (assignment.ends_at and assignment.ends_at <= now): return False
    if assignment.weekdays and now.weekday() not in assignment.weekdays: return False
    current = now.time().replace(tzinfo=None)
    try:
        if assignment.daily_start and current < time.fromisoformat(assignment.daily_start): return False
        if assignment.daily_end and current >= time.fromisoformat(assignment.daily_end): return False
    except ValueError: return False
    return True


@router.get("/players/{player_id}/preview")
def player_preview(player_id: str, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found.")
    require(user, "view", PLAYER, player.id, db); layout = db.get(Layout, player.layout_id) if player.layout_id else None; now = datetime.now(UTC); destinations = [player.id] + ([zone.id for zone in layout.zones if zone.enabled] if layout else [])
    items = []
    for assignment in db.scalars(select(ContentAssignment).where(ContentAssignment.destination_id.in_(destinations))):
        content = db.get(Content, assignment.content_id); published = db.scalar(select(ContentVersion).where(ContentVersion.content_id == assignment.content_id, ContentVersion.state == "published"))
        if content and published and eligible(assignment, now): items.append({"assignment": assignment_data(assignment), "content": {"id": content.id, "name": content.name, "revision": version_data(published)}, "destination_type": assignment.destination_type})
    return {"kind": "server_desired_state", "player": player_data(player), "layout": layout_data(layout) if layout else None, "eligible_assignments": sorted(items, key=lambda item: item["assignment"]["priority"], reverse=True), "generated_at": now}
