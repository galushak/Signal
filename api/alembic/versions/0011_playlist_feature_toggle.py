"""Disable the optional playlist feature by default.

Revision ID: 0011_playlist_feature_toggle
Revises: 0010_playlists
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_playlist_feature_toggle"
down_revision = "0010_playlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("playlists_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "playlists_enabled")
