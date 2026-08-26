"""Add the user-facing direct-media display mode.

Revision ID: 0007_display_mode
Revises: 0006_default_full_screen
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_display_mode"
down_revision = "0006_default_full_screen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_assignments", sa.Column("display_mode", sa.String(length=16), nullable=False, server_default="fit"))
    op.alter_column("content_assignments", "display_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("content_assignments", "display_mode")
