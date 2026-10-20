"""DB2 phase/turn_player NOT NULL+CHECK; DB6 imutabilidade de game_events

Revision ID: 0015_db2_db6
Revises: 0014_rules_round2
Create Date: 2026-10-20
"""

from alembic import op

revision = "0015_db2_db6"
down_revision = "0014_rules_round2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE faction_round_states
          SET phase = COALESCE(phase, 'command'),
              turn_player = COALESCE(turn_player, player);
        ALTER TABLE faction_round_states
          ALTER COLUMN phase SET NOT NULL,
          ALTER COLUMN turn_player SET NOT NULL;
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS faction_round_states_phase_check;
        ALTER TABLE faction_round_states
          ADD CONSTRAINT faction_round_states_phase_check
          CHECK (phase IN (
            'round_start','command','battle_shock','movement','shooting','charge',
            'fight','end_of_turn','end_of_round'
          ));
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS faction_round_states_turn_player_check;
        ALTER TABLE faction_round_states
          ADD CONSTRAINT faction_round_states_turn_player_check
          CHECK (turn_player IN ('me','opponent'));

        CREATE OR REPLACE FUNCTION game_events_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'game_events é imutável (DB6)';
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS trg_game_events_immutable ON game_events;
        CREATE TRIGGER trg_game_events_immutable
          BEFORE UPDATE ON game_events
          FOR EACH ROW EXECUTE PROCEDURE game_events_immutable();

        CREATE UNIQUE INDEX IF NOT EXISTS uq_game_events_game_id_id
          ON game_events (game_id, id);
        ALTER TABLE game_events DROP CONSTRAINT IF EXISTS game_events_undoes_same_game_fkey;
        ALTER TABLE game_events
          ADD CONSTRAINT game_events_undoes_same_game_fkey
          FOREIGN KEY (game_id, undoes_event_id)
          REFERENCES game_events (game_id, id)
          DEFERRABLE INITIALLY DEFERRED;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE game_events DROP CONSTRAINT IF EXISTS game_events_undoes_same_game_fkey;
        DROP TRIGGER IF EXISTS trg_game_events_immutable ON game_events;
        DROP FUNCTION IF EXISTS game_events_immutable();
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS faction_round_states_phase_check;
        ALTER TABLE faction_round_states DROP CONSTRAINT IF EXISTS faction_round_states_turn_player_check;
        ALTER TABLE faction_round_states
          ALTER COLUMN phase DROP NOT NULL,
          ALTER COLUMN turn_player DROP NOT NULL;
        """
    )
