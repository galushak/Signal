"""Create Signal's protected Full Screen system layout.

Revision ID: 0006_default_full_screen
Revises: 0005_player_archive
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_default_full_screen"
down_revision = "0005_player_archive"
branch_labels = None
depends_on = None

FULL_SCREEN_ID = "00000000-0000-4000-8000-000000000001"
MAIN_ZONE_ID = "00000000-0000-4000-8000-000000000002"


def upgrade():
    op.add_column("layouts", sa.Column("system_key", sa.String(48), nullable=True))
    op.create_index("ix_layouts_system_key", "layouts", ["system_key"], unique=True)
    # A real user always exists before a deployment can contain players. This
    # keeps the built-in layout compatible with the existing authored-layout FK.
    op.execute(
        """
        INSERT INTO layouts (id, name, description, logical_width, logical_height, enabled, locked, system_key, created_by_id)
        SELECT '00000000-0000-4000-8000-000000000001', 'Full Screen',
               'Signal system fallback layout.', 1920, 1080, true, true,
               'full-screen', id
        FROM users
        ORDER BY super_admin DESC, created_at
        LIMIT 1
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO zones (id, layout_id, name, x, y, width, height, z_index, enabled, locked)
        SELECT '00000000-0000-4000-8000-000000000002',
               '00000000-0000-4000-8000-000000000001',
               'Main', 0, 0, 1920, 1080, 0, true, true
        WHERE EXISTS (SELECT 1 FROM layouts WHERE id = '00000000-0000-4000-8000-000000000001')
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade():
    op.drop_index("ix_layouts_system_key", table_name="layouts")
    op.drop_column("layouts", "system_key")
