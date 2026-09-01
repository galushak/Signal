"""Replace grant-based access with roles and add player command payloads.

Revision ID: 0009_roles_player_controls
Revises: 0008_first_run_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_roles_player_controls"
down_revision = "0008_first_run_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=32), nullable=False, server_default="user"))
    op.add_column("player_commands", sa.Column("payload", sa.JSON(), nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE users SET role = 'super_admin' WHERE super_admin = true"))
    bind.execute(sa.text("""
        UPDATE users SET role = 'admin'
        WHERE super_admin = false AND id IN (
          SELECT DISTINCT user_id FROM permission_grants
          WHERE capability IN ('manage_players', 'manage_layouts', 'manage_settings', 'manage_users', 'manage_permissions')
        )
    """))
    bind.execute(sa.text("""
        UPDATE users SET role = 'uploader_creator'
        WHERE role = 'user' AND id IN (
          SELECT DISTINCT user_id FROM permission_grants
          WHERE capability IN ('upload_media', 'manage_media', 'create_content', 'edit_content', 'publish')
        )
    """))


def downgrade() -> None:
    op.drop_column("player_commands", "payload")
    op.drop_column("users", "role")
