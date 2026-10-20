"""Shadow of Chaos por fase e area

Revision ID: 0013_shadow_phase
Revises: 0012_game_result
Create Date: 2026-10-20
"""

from alembic import op

revision = "0013_shadow_phase"
down_revision = "0012_game_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE faction_round_states
          ADD COLUMN IF NOT EXISTS phase TEXT,
          ADD COLUMN IF NOT EXISTS turn_player TEXT,
          ADD COLUMN IF NOT EXISTS nml_in_shadow BOOLEAN,
          ADD COLUMN IF NOT EXISTS opp_dz_in_shadow BOOLEAN;
        UPDATE faction_round_states
          SET phase = COALESCE(phase, 'command'),
              turn_player = COALESCE(turn_player, player),
              nml_in_shadow = COALESCE(nml_in_shadow, whole_board, false),
              opp_dz_in_shadow = COALESCE(opp_dz_in_shadow, whole_board, false);
        ALTER TABLE faction_round_states
          ALTER COLUMN phase SET DEFAULT 'command',
          ALTER COLUMN turn_player SET DEFAULT 'me';
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS faction_round_states_game_id_round_player_state_key_key;
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS uq_faction_round_states_key;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_faction_round_states_phase
          ON faction_round_states (game_id, round, turn_player, phase, state_key);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_faction_round_states_phase;
        ALTER TABLE faction_round_states
          DROP COLUMN IF EXISTS phase,
          DROP COLUMN IF EXISTS turn_player,
          DROP COLUMN IF EXISTS nml_in_shadow,
          DROP COLUMN IF EXISTS opp_dz_in_shadow;
        CREATE UNIQUE INDEX IF NOT EXISTS faction_round_states_game_id_round_player_state_key_key
          ON faction_round_states (game_id, round, player, state_key);
        """
    )
