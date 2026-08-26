"""Flip enrollment records to server-generated, player-bound codes.

Revision ID: 0004_server_generated_enrollment
Revises: 0003_player_runtime
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_server_generated_enrollment"
down_revision = "0003_player_runtime"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL names the inline unique constraint this way. IF EXISTS makes
    # the migration safe for databases created from a later metadata snapshot.
    op.execute("ALTER TABLE player_enrollments DROP CONSTRAINT IF EXISTS player_enrollments_device_identifier_key")
    op.alter_column("player_enrollments", "device_identifier", existing_type=sa.String(255), nullable=True)
    op.add_column("player_enrollments", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("player_enrollments", sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id")))
    op.add_column("player_enrollments", sa.Column("display_code", sa.String(16)))
    op.create_index("ix_player_enrollments_created_by_id", "player_enrollments", ["created_by_id"])


def downgrade():
    op.drop_index("ix_player_enrollments_created_by_id", table_name="player_enrollments")
    op.drop_column("player_enrollments", "display_code")
    op.drop_column("player_enrollments", "created_by_id")
    op.drop_column("player_enrollments", "cancelled_at")
    op.alter_column("player_enrollments", "device_identifier", existing_type=sa.String(255), nullable=False)
    op.create_unique_constraint("player_enrollments_device_identifier_key", "player_enrollments", ["device_identifier"])
