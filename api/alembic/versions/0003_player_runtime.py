"""Player enrollment, device credentials and runtime state.

Revision ID: 0003_player_runtime
Revises: 0002_layouts_content
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_player_runtime"
down_revision = "0002_layouts_content"
branch_labels = None
depends_on = None


def ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)]


def upgrade():
    op.add_column("players", sa.Column("device_secret_hash", sa.String(255)))
    op.add_column("players", sa.Column("desired_state_revision", sa.String(128)))
    op.add_column("players", sa.Column("applied_state_revision", sa.String(128)))
    op.add_column("players", sa.Column("runtime_data", sa.JSON()))
    op.create_table("player_enrollments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("code_hash", sa.String(255), nullable=False), sa.Column("device_identifier", sa.String(255), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("claimed_at", sa.DateTime(timezone=True)), sa.Column("delivered_at", sa.DateTime(timezone=True)), sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id")), sa.Column("credential_delivery_secret", sa.String(255)), *ts())
    op.create_index("ix_player_enrollments_code_hash", "player_enrollments", ["code_hash"])
    op.create_index("ix_player_enrollments_device_identifier", "player_enrollments", ["device_identifier"])
    op.create_index("ix_player_enrollments_expires_at", "player_enrollments", ["expires_at"])
    op.create_index("ix_player_enrollments_player_id", "player_enrollments", ["player_id"])
    op.create_table("player_commands", sa.Column("id", sa.String(36), primary_key=True), sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False), sa.Column("command", sa.String(48), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="queued"), sa.Column("result", sa.JSON()), sa.Column("requested_by_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("completed_at", sa.DateTime(timezone=True)), *ts())
    op.create_index("ix_player_commands_player_id", "player_commands", ["player_id"])


def downgrade():
    op.drop_index("ix_player_commands_player_id", table_name="player_commands")
    op.drop_table("player_commands")
    for name in ("ix_player_enrollments_player_id", "ix_player_enrollments_expires_at", "ix_player_enrollments_device_identifier", "ix_player_enrollments_code_hash"):
        op.drop_index(name, table_name="player_enrollments")
    op.drop_table("player_enrollments")
    for name in ("runtime_data", "applied_state_revision", "desired_state_revision", "device_secret_hash"):
        op.drop_column("players", name)
