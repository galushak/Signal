"""Add durable first-run state and the small V1 application settings model.

Revision ID: 0008_first_run_settings
Revises: 0007_display_mode
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_first_run_settings"
down_revision = "0007_display_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_name", sa.String(length=160), nullable=False, server_default="Signal"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("default_slide_duration_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Existing installs already have a usable administrator.  Preserve that
    # state rather than ever sending them back through browser setup.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM users LIMIT 1")).scalar() is not None:
        bind.execute(sa.text("""
            INSERT INTO app_settings
              (id, organization_name, timezone, default_slide_duration_seconds, setup_completed_at)
            VALUES (1, 'Signal', 'UTC', 20, CURRENT_TIMESTAMP)
        """))


def downgrade() -> None:
    op.drop_table("app_settings")
