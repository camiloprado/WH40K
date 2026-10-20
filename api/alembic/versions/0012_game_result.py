"""resultado da partida e histórico que não segura a lista

Revision ID: 0012_game_result
Revises: 0011_round_start
Create Date: 2026-10-15
"""

from alembic import op

revision = "0012_game_result"
down_revision = "0011_round_start"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE games DROP CONSTRAINT IF EXISTS games_list_version_id_fkey;
        ALTER TABLE games ALTER COLUMN list_version_id DROP NOT NULL;
        ALTER TABLE games
          ADD CONSTRAINT games_list_version_id_fkey
          FOREIGN KEY (list_version_id) REFERENCES list_versions(id) ON DELETE SET NULL;
        ALTER TABLE games
          ADD COLUMN result TEXT CHECK (result IS NULL OR result IN ('win','loss','draw')),
          ADD COLUMN list_label TEXT CHECK (list_label IS NULL OR length(list_label) <= 200);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM games WHERE list_version_id IS NULL) THEN
            RAISE EXCEPTION 'DB5: downgrade 0012 apagaria games sem lista; restaure o snapshot (S3)';
          END IF;
        END $$;
        ALTER TABLE games DROP CONSTRAINT IF EXISTS games_list_version_id_fkey;
        ALTER TABLE games ALTER COLUMN list_version_id SET NOT NULL;
        ALTER TABLE games
          ADD CONSTRAINT games_list_version_id_fkey
          FOREIGN KEY (list_version_id) REFERENCES list_versions(id);
        ALTER TABLE games DROP COLUMN IF EXISTS list_label, DROP COLUMN IF EXISTS result;
        """
    )
