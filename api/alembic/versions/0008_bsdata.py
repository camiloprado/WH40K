"""origem bsdata no catálogo e histórico de importações

Revision ID: 0008_bsdata
Revises: 0007_home_lane
Create Date: 2026-10-15
"""

from alembic import op

revision = "0008_bsdata"
down_revision = "0007_home_lane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE abilities
          ADD COLUMN source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','bsdata')),
          ADD COLUMN source_ref TEXT CHECK (length(source_ref) <= 300);
        ALTER TABLE detachments
          ADD COLUMN source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','import','bsdata')),
          ADD COLUMN source_ref TEXT CHECK (length(source_ref) <= 300);
        ALTER TABLE enhancements
          ADD COLUMN source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','bsdata')),
          ADD COLUMN source_ref TEXT CHECK (length(source_ref) <= 300);
        ALTER TABLE weapons
          ADD COLUMN source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','import','bsdata'));
        UPDATE weapons SET source = 'import'
          WHERE datasheet_id IN (SELECT id FROM datasheets WHERE source = 'import');
        UPDATE detachments SET source = 'import';
        ALTER TABLE rule_effects
          ADD COLUMN source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','bsdata'));

        CREATE TABLE bsdata_imports (
          id BIGSERIAL PRIMARY KEY,
          repo TEXT NOT NULL CHECK (repo ~ '^wh40k-[0-9]{1,2}e$'),
          sha CHAR(40) NOT NULL CHECK (sha ~ '^[0-9a-f]{40}$'),
          catalogue TEXT NOT NULL CHECK (length(catalogue) <= 200),
          revision INTEGER,
          faction_id BIGINT REFERENCES factions(id) ON DELETE SET NULL,
          summary JSONB NOT NULL DEFAULT '{}',
          imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_bsdata_imports_faction_id ON bsdata_imports (faction_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS bsdata_imports;
        ALTER TABLE rule_effects DROP COLUMN IF EXISTS source;
        ALTER TABLE weapons DROP COLUMN IF EXISTS source;
        ALTER TABLE enhancements DROP COLUMN IF EXISTS source_ref, DROP COLUMN IF EXISTS source;
        ALTER TABLE detachments DROP COLUMN IF EXISTS source_ref, DROP COLUMN IF EXISTS source;
        ALTER TABLE abilities DROP COLUMN IF EXISTS source_ref, DROP COLUMN IF EXISTS source;
        """
    )
