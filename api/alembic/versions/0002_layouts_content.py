"""Layouts, zones, versioned content, templates and assignments.

Revision ID: 0002_layouts_content
Revises: 0001_functional_core
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_layouts_content"
down_revision = "0001_functional_core"
branch_labels = None
depends_on = None


def ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)]


def upgrade():
    op.create_table("layouts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False, unique=True), sa.Column("description", sa.Text()), sa.Column("logical_width", sa.Integer(), nullable=False, server_default="1920"), sa.Column("logical_height", sa.Integer(), nullable=False, server_default="1080"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("trashed_at", sa.DateTime(timezone=True)), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), *ts())
    op.create_table("layout_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("layout_id", sa.String(36), sa.ForeignKey("layouts.id", ondelete="CASCADE"), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("definition", sa.JSON(), nullable=False), sa.Column("note", sa.Text()), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("layout_id", "revision", name="uq_layout_revision"))
    op.create_index("ix_layout_versions_layout_id", "layout_versions", ["layout_id"])
    op.create_table("zones", sa.Column("id", sa.String(36), primary_key=True), sa.Column("layout_id", sa.String(36), sa.ForeignKey("layouts.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("x", sa.Integer(), nullable=False, server_default="0"), sa.Column("y", sa.Integer(), nullable=False, server_default="0"), sa.Column("width", sa.Integer(), nullable=False, server_default="1920"), sa.Column("height", sa.Integer(), nullable=False, server_default="1080"), sa.Column("z_index", sa.Integer(), nullable=False, server_default="0"), sa.Column("background", sa.String(64)), sa.Column("border", sa.JSON()), sa.Column("padding", sa.Integer(), nullable=False, server_default="0"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()), *ts())
    op.create_index("ix_zones_layout_id", "zones", ["layout_id"])
    op.add_column("players", sa.Column("layout_id", sa.String(36), sa.ForeignKey("layouts.id")))
    op.create_index("ix_players_layout_id", "players", ["layout_id"])
    op.create_table("content", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("content_type", sa.String(48), nullable=False, server_default="design"), sa.Column("scope_type", sa.String(32), nullable=False, server_default="district"), sa.Column("scope_id", sa.String(36)), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("trashed_at", sa.DateTime(timezone=True)), *ts())
    op.create_table("content_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("content_id", sa.String(36), sa.ForeignKey("content.id", ondelete="CASCADE"), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("state", sa.String(24), nullable=False, server_default="draft"), sa.Column("design_document", sa.JSON(), nullable=False), sa.Column("note", sa.Text()), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("content_id", "revision", name="uq_content_revision"))
    op.create_index("ix_content_versions_content_id", "content_versions", ["content_id"])
    op.create_table("content_assignments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("content_id", sa.String(36), sa.ForeignKey("content.id", ondelete="CASCADE"), nullable=False), sa.Column("destination_type", sa.String(16), nullable=False), sa.Column("destination_id", sa.String(36), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("priority", sa.Integer(), nullable=False, server_default="1"), sa.Column("duration_seconds", sa.Integer()), sa.Column("transition", sa.String(16)), sa.Column("starts_at", sa.DateTime(timezone=True)), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("weekdays", sa.JSON()), sa.Column("daily_start", sa.String(8)), sa.Column("daily_end", sa.String(8)), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), *ts())
    op.create_index("ix_content_assignments_content_id", "content_assignments", ["content_id"])
    op.create_index("ix_content_assignments_destination_id", "content_assignments", ["destination_id"])
    op.create_table("content_templates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False, unique=True), sa.Column("design_document", sa.JSON(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("trashed_at", sa.DateTime(timezone=True)), sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), *ts())


def downgrade():
    op.drop_table("content_templates")
    op.drop_index("ix_content_assignments_destination_id", table_name="content_assignments")
    op.drop_index("ix_content_assignments_content_id", table_name="content_assignments")
    op.drop_table("content_assignments")
    op.drop_index("ix_content_versions_content_id", table_name="content_versions")
    op.drop_table("content_versions")
    op.drop_table("content")
    op.drop_index("ix_players_layout_id", table_name="players")
    op.drop_column("players", "layout_id")
    op.drop_index("ix_zones_layout_id", table_name="zones")
    op.drop_table("zones")
    op.drop_index("ix_layout_versions_layout_id", table_name="layout_versions")
    op.drop_table("layout_versions")
    op.drop_table("layouts")
