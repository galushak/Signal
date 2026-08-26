"""Archive displays safely and support ordered media assignments.

Revision ID: 0005_player_archive
Revises: 0004_server_generated_enrollment
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_player_archive"
down_revision = "0004_server_generated_enrollment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("players", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("players", sa.Column("archived_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_players_archived_at", "players", ["archived_at"])
    op.create_index("ix_players_archived_by_id", "players", ["archived_by_id"])

    op.alter_column("content_assignments", "content_id", existing_type=sa.String(36), nullable=True)
    op.add_column("content_assignments", sa.Column("media_asset_id", sa.String(32), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True))
    op.add_column("content_assignments", sa.Column("source_type", sa.String(16), nullable=False, server_default="content"))
    op.add_column("content_assignments", sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_content_assignments_media_asset_id", "content_assignments", ["media_asset_id"])
    op.execute("UPDATE content_assignments SET source_type = 'content' WHERE source_type IS NULL")
    op.alter_column("content_assignments", "source_type", server_default=None)
    op.alter_column("content_assignments", "position", server_default=None)


def downgrade():
    op.drop_index("ix_content_assignments_media_asset_id", table_name="content_assignments")
    op.drop_column("content_assignments", "position")
    op.drop_column("content_assignments", "source_type")
    op.drop_column("content_assignments", "media_asset_id")
    op.alter_column("content_assignments", "content_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("ix_players_archived_by_id", table_name="players")
    op.drop_index("ix_players_archived_at", table_name="players")
    op.drop_column("players", "archived_by_id")
    op.drop_column("players", "archived_at")
