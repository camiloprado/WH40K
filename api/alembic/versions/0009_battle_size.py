"""tipo de jogo e teto de pontos da lista

Revision ID: 0009_battle_size
Revises: 0008_bsdata
Create Date: 2026-10-15
"""

from alembic import op

revision = "0009_battle_size"
down_revision = "0008_bsdata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE list_versions
          ADD COLUMN battle_size TEXT CHECK (battle_size IS NULL OR length(battle_size) <= 80),
          ADD COLUMN points_limit INT CHECK (points_limit IS NULL OR points_limit BETWEEN 0 AND 100000);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE list_versions
          DROP COLUMN IF EXISTS points_limit,
          DROP COLUMN IF EXISTS battle_size;
        """
    )
