"""checagem de armas

Revision ID: 0004_arms
Revises: 0003_games
Create Date: 2026-10-15
"""

from alembic import op

revision = "0004_arms"
down_revision = "0003_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE target_profiles (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          toughness SMALLINT NOT NULL CHECK (toughness >= 1),
          save SMALLINT NOT NULL CHECK (save BETWEEN 2 AND 6),
          invuln SMALLINT CHECK (invuln BETWEEN 2 AND 6),
          wounds SMALLINT NOT NULL CHECK (wounds >= 1),
          fnp SMALLINT CHECK (fnp BETWEEN 2 AND 6),
          models SMALLINT NOT NULL DEFAULT 1 CHECK (models >= 1),
          keywords TEXT[] NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE weapon_check_marks (
          list_unit_id BIGINT PRIMARY KEY REFERENCES list_units(id) ON DELETE CASCADE,
          checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          chosen_loadout_label TEXT
        );

        CREATE TRIGGER trg_target_profiles_updated BEFORE UPDATE ON target_profiles
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS weapon_check_marks, target_profiles CASCADE;")
