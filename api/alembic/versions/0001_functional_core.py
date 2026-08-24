"""Functional core schema.

Revision ID: 0001_functional_core
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_functional_core"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("username", sa.String(80), nullable=False, unique=True), sa.Column("display_name", sa.String(160), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("super_admin", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("last_login_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_users_username", "users", ["username"])
    op.create_table("auth_sessions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table("buildings", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False, unique=True), sa.Column("description", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), *timestamps())
    op.create_table("players", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("building_id", sa.String(36), sa.ForeignKey("buildings.id"), nullable=False), sa.Column("description", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("enrollment_status", sa.String(32), nullable=False, server_default="manual"), sa.Column("enrollment_code_hash", sa.String(255)), sa.Column("enrollment_expires_at", sa.DateTime(timezone=True)), sa.Column("device_identifier", sa.String(255), unique=True), sa.Column("last_seen_at", sa.DateTime(timezone=True)), sa.Column("software_version", sa.String(80)), sa.Column("network_info", sa.JSON()), sa.Column("resolution", sa.String(32)), sa.Column("health_state", sa.String(32), nullable=False, server_default="never_connected"), sa.Column("cache_state", sa.String(32), nullable=False, server_default="unknown"), *timestamps())
    op.create_index("ix_players_building_id", "players", ["building_id"])
    op.create_table("media_folders", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("parent_id", sa.String(36), sa.ForeignKey("media_folders.id")), sa.Column("scope_type", sa.String(32), nullable=False, server_default="district"), sa.Column("scope_id", sa.String(36)), *timestamps())
    op.create_table("tags", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(80), nullable=False, unique=True), *timestamps())
    op.create_table("media_assets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("media_type", sa.String(32), nullable=False), sa.Column("mime_type", sa.String(127), nullable=False), sa.Column("original_path", sa.String(512), nullable=False), sa.Column("processed_path", sa.String(512)), sa.Column("thumbnail_path", sa.String(512)), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("processing_state", sa.String(32), nullable=False, server_default="processing"), sa.Column("processing_error", sa.Text()), sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("duration_seconds", sa.Integer()), sa.Column("scope_type", sa.String(32), nullable=False, server_default="district"), sa.Column("scope_id", sa.String(36)), sa.Column("folder_id", sa.String(36), sa.ForeignKey("media_folders.id")), sa.Column("uploaded_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("trashed_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_table("media_asset_tags", sa.Column("asset_id", sa.String(36), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True), sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("permission_grants", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("capability", sa.String(80), nullable=False), sa.Column("scope_type", sa.String(32), nullable=False, server_default="district"), sa.Column("scope_id", sa.String(36)), *timestamps(), sa.UniqueConstraint("user_id", "capability", "scope_type", "scope_id", name="uq_permission_grant"))
    op.create_index("ix_permission_grants_user_id", "permission_grants", ["user_id"])
    op.create_index("ix_permission_grants_capability", "permission_grants", ["capability"])
    op.create_table("audit_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("action", sa.String(160), nullable=False), sa.Column("resource_type", sa.String(80), nullable=False), sa.Column("resource_id", sa.String(36)), sa.Column("resource_name", sa.String(255)), sa.Column("scope_type", sa.String(32)), sa.Column("scope_id", sa.String(36)), sa.Column("source_ip", sa.String(64)), sa.Column("metadata_json", sa.JSON()))
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"])


def downgrade() -> None:
    for table in ("audit_events", "permission_grants", "media_asset_tags", "media_assets", "tags", "media_folders", "players", "buildings", "auth_sessions", "users"):
        op.drop_table(table)
