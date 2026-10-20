"""habilidade vinda do import do New Recruit

Revision ID: 0010_ability_import
Revises: 0009_battle_size
Create Date: 2026-10-15
"""

from alembic import op

revision = "0010_ability_import"
down_revision = "0009_battle_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE abilities DROP CONSTRAINT IF EXISTS abilities_source_check;
        ALTER TABLE abilities ADD CONSTRAINT abilities_source_check
          CHECK (source IN ('user','bsdata','import'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE abilities SET source = 'user' WHERE source = 'import';
        ALTER TABLE abilities DROP CONSTRAINT IF EXISTS abilities_source_check;
        ALTER TABLE abilities ADD CONSTRAINT abilities_source_check
          CHECK (source IN ('user','bsdata'));
        """
    )
