"""mapas

Revision ID: 0005_maps
Revises: 0004_arms
Create Date: 2026-10-15
"""

from alembic import op

revision = "0005_maps"
down_revision = "0004_arms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE missions (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          deployment_type TEXT,
          board_w_in SMALLINT NOT NULL DEFAULT 60 CHECK (board_w_in BETWEEN 12 AND 120),
          board_h_in SMALLINT NOT NULL DEFAULT 44 CHECK (board_h_in BETWEEN 12 AND 120),
          zones_json JSONB NOT NULL DEFAULT '[]',
          objectives_json JSONB NOT NULL DEFAULT '[]',
          primary_summary TEXT CHECK (length(primary_summary) <= 4000),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        ALTER TABLE games
          ADD CONSTRAINT fk_games_mission_id FOREIGN KEY (mission_id) REFERENCES missions(id);

        CREATE TABLE maps (
          id BIGSERIAL PRIMARY KEY,
          list_version_id BIGINT NOT NULL REFERENCES list_versions(id) ON DELETE CASCADE,
          mission_id BIGINT REFERENCES missions(id),
          name TEXT NOT NULL,
          side TEXT CHECK (side IN ('attacker','defender')),
          terrain_json JSONB NOT NULL DEFAULT '[]',
          notes TEXT CHECK (length(notes) <= 10000),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (id, list_version_id)
        );
        CREATE INDEX ix_maps_list_version_id ON maps (list_version_id);
        CREATE INDEX ix_maps_mission_id ON maps (mission_id);

        CREATE TABLE map_placements (
          id BIGSERIAL PRIMARY KEY,
          map_id BIGINT NOT NULL,
          list_version_id BIGINT NOT NULL,
          list_unit_id BIGINT NOT NULL,
          x_in NUMERIC(5,2),
          y_in NUMERIC(5,2),
          rotation_deg NUMERIC(5,1) NOT NULL DEFAULT 0,
          state TEXT NOT NULL DEFAULT 'on_table' CHECK (state IN ('on_table','reserves','deep_strike','embarked')),
          first_target TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (map_id, list_unit_id),
          FOREIGN KEY (map_id, list_version_id) REFERENCES maps (id, list_version_id) ON DELETE CASCADE,
          FOREIGN KEY (list_unit_id, list_version_id) REFERENCES list_units (id, list_version_id) ON DELETE CASCADE
        );
        CREATE INDEX ix_map_placements_map ON map_placements (map_id, list_version_id);
        CREATE INDEX ix_map_placements_unit ON map_placements (list_unit_id, list_version_id);

        CREATE TRIGGER trg_missions_updated BEFORE UPDATE ON missions
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_maps_updated BEFORE UPDATE ON maps
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_map_placements_updated BEFORE UPDATE ON map_placements
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS map_placements, maps CASCADE;
        ALTER TABLE games DROP CONSTRAINT IF EXISTS fk_games_mission_id;
        DROP TABLE IF EXISTS missions CASCADE;
        """
    )
