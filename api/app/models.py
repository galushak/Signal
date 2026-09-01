import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppSettings(Timestamped, Base):
    """The single, user-facing configuration record for a Signal install."""

    __tablename__ = "app_settings"
    # A fixed primary key makes the singleton guarantee database-enforced.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    organization_name: Mapped[str] = mapped_column(String(160), default="Signal")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    default_slide_duration_seconds: Mapped[int] = mapped_column(Integer, default=20)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(32), default="user", server_default="user")
    super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grants: Mapped[list["PermissionGrant"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship()


class Building(Timestamped, Base):
    __tablename__ = "buildings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    players: Mapped[list["Player"]] = relationship(back_populates="building")


class Player(Timestamped, Base):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    building_id: Mapped[str] = mapped_column(ForeignKey("buildings.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enrollment_status: Mapped[str] = mapped_column(String(32), default="manual")
    enrollment_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_identifier: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    software_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    network_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    layout_id: Mapped[str | None] = mapped_column(ForeignKey("layouts.id"), nullable=True, index=True)
    health_state: Mapped[str] = mapped_column(String(32), default="never_connected")
    cache_state: Mapped[str] = mapped_column(String(32), default="unknown")
    device_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    desired_state_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    applied_state_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    building: Mapped[Building] = relationship(back_populates="players")


class PlayerEnrollment(Timestamped, Base):
    __tablename__ = "player_enrollments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code_hash: Mapped[str] = mapped_column(String(255), index=True)
    # The server prepares this record before a physical player exists. The
    # device identifier is supplied only when that player redeems the code.
    device_identifier: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"), nullable=True, index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # Kept only for the pending 15-minute lifecycle so an authorized admin can
    # revisit/copy the code. Device validation always uses code_hash.
    display_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    credential_delivery_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PlayerCommand(Timestamped, Base):
    __tablename__ = "player_commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    command: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaFolder(Timestamped, Base):
    __tablename__ = "media_folders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("media_folders.id"), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="district")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Tag(Timestamped, Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class MediaAsset(Timestamped, Base):
    __tablename__ = "media_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    display_name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(127))
    original_path: Mapped[str] = mapped_column(String(512))
    processed_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer)
    processing_state: Mapped[str] = mapped_column(String(32), default="processing")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="district")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("media_folders.id"), nullable=True)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list["MediaAssetTag"]] = relationship(cascade="all, delete-orphan")


class MediaAssetTag(Base):
    __tablename__ = "media_asset_tags"
    asset_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Layout(Timestamped, Base):
    __tablename__ = "layouts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logical_width: Mapped[int] = mapped_column(Integer, default=1920)
    logical_height: Mapped[int] = mapped_column(Integer, default=1080)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    system_key: Mapped[str | None] = mapped_column(String(48), unique=True, nullable=True, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    zones: Mapped[list["Zone"]] = relationship(back_populates="layout", cascade="all, delete-orphan")


class LayoutVersion(Base):
    __tablename__ = "layout_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    layout_id: Mapped[str] = mapped_column(ForeignKey("layouts.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("layout_id", "revision", name="uq_layout_revision"),)


class Zone(Timestamped, Base):
    __tablename__ = "zones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    layout_id: Mapped[str] = mapped_column(ForeignKey("layouts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    z_index: Mapped[int] = mapped_column(Integer, default=0)
    background: Mapped[str | None] = mapped_column(String(64), nullable=True)
    border: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    padding: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    layout: Mapped["Layout"] = relationship(back_populates="zones")


class Content(Timestamped, Base):
    __tablename__ = "content"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(48), default="design")
    scope_type: Mapped[str] = mapped_column(String(32), default="district")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentVersion(Base):
    __tablename__ = "content_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    content_id: Mapped[str] = mapped_column(ForeignKey("content.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    design_document: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("content_id", "revision", name="uq_content_revision"),)


class ContentAssignment(Timestamped, Base):
    __tablename__ = "content_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    content_id: Mapped[str | None] = mapped_column(ForeignKey("content.id", ondelete="CASCADE"), index=True, nullable=True)
    media_asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), default="content")
    destination_type: Mapped[str] = mapped_column(String(16))
    destination_id: Mapped[str] = mapped_column(String(36), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    display_mode: Mapped[str] = mapped_column(String(16), default="fit")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weekdays: Mapped[list | None] = mapped_column(JSON, nullable=True)
    daily_start: Mapped[str | None] = mapped_column(String(8), nullable=True)
    daily_end: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ContentTemplate(Timestamped, Base):
    __tablename__ = "content_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    design_document: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class PermissionGrant(Timestamped, Base):
    __tablename__ = "permission_grants"
    __table_args__ = (UniqueConstraint("user_id", "capability", "scope_type", "scope_id", name="uq_permission_grant"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    capability: Mapped[str] = mapped_column(String(80), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="district")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user: Mapped[User] = relationship(back_populates="grants")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
