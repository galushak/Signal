"""Add scheduled playlists that preserve base display rotations.

Revision ID: 0010_playlists
Revises: 0009_roles_player_controls
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_playlists"
down_revision = "0009_roles_player_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="announcement"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "playlist_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("playlist_id", sa.String(length=36), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_id", sa.String(length=36), sa.ForeignKey("content.id", ondelete="CASCADE"), nullable=True),
        sa.Column("media_asset_id", sa.String(length=36), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_playlist_items_playlist_id", "playlist_items", ["playlist_id"])
    op.create_table(
        "playlist_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("playlist_id", sa.String(length=36), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_type", sa.String(length=16), nullable=False),
        sa.Column("destination_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weekdays", sa.JSON(), nullable=True),
        sa.Column("daily_start", sa.String(length=8), nullable=True),
        sa.Column("daily_end", sa.String(length=8), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_playlist_assignments_playlist_id", "playlist_assignments", ["playlist_id"])
    op.create_index("ix_playlist_assignments_destination_id", "playlist_assignments", ["destination_id"])


def downgrade() -> None:
    op.drop_table("playlist_assignments")
    op.drop_table("playlist_items")
    op.drop_table("playlists")
