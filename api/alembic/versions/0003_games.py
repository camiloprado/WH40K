"""partidas

Revision ID: 0003_games
Revises: 0002_effects
Create Date: 2026-10-15
"""

from alembic import op

revision = "0003_games"
down_revision = "0002_effects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE games (
          id UUID PRIMARY KEY,
          list_version_id BIGINT NOT NULL REFERENCES list_versions(id),
          bundle_etag TEXT NOT NULL,
          opponent_name TEXT CHECK (length(opponent_name) <= 200),
          opponent_faction TEXT CHECK (length(opponent_faction) <= 200),
          mission_name TEXT CHECK (length(mission_name) <= 200),
          mission_id BIGINT,
          first_player TEXT NOT NULL CHECK (first_player IN ('me','opponent')),
          status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','finished','abandoned')),
          current_round SMALLINT NOT NULL DEFAULT 1 CHECK (current_round BETWEEN 1 AND 10),
          current_player TEXT NOT NULL CHECK (current_player IN ('me','opponent')),
          current_phase TEXT NOT NULL DEFAULT 'command' CHECK (current_phase IN ('command','battle_shock','movement','shooting','charge','fight','end_of_turn')),
          cp_me SMALLINT NOT NULL DEFAULT 0 CHECK (cp_me BETWEEN 0 AND 99),
          cp_opponent SMALLINT CHECK (cp_opponent BETWEEN 0 AND 99),
          vp_me SMALLINT NOT NULL DEFAULT 0,
          vp_opponent SMALLINT NOT NULL DEFAULT 0,
          last_seq INT NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (id, list_version_id)
        );
        CREATE INDEX ix_games_list_version_id ON games (list_version_id);
        CREATE INDEX ix_games_mission_id ON games (mission_id);

        CREATE TABLE game_events (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          seq INT NOT NULL CHECK (seq >= 1),
          device_id TEXT NOT NULL CHECK (length(device_id) <= 64),
          type TEXT NOT NULL CHECK (type IN ('game_started','phase_advanced','unit_state_set','cp_changed','stratagem_used','objective_set','vp_scored','shadow_set','battleshock_result','undo','game_ended')),
          payload JSONB NOT NULL CHECK (octet_length(payload::text) <= 8192),
          undoes_event_id UUID REFERENCES game_events(id),
          created_at TIMESTAMPTZ NOT NULL,
          received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (game_id, device_id, seq)
        );
        CREATE INDEX ix_game_events_game_seq ON game_events (game_id, seq);
        CREATE INDEX ix_game_events_undoes ON game_events (undoes_event_id);

        CREATE TABLE game_turns (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          round SMALLINT NOT NULL CHECK (round BETWEEN 1 AND 10),
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          phase TEXT NOT NULL CHECK (phase IN ('command','battle_shock','movement','shooting','charge','fight','end_of_turn')),
          started_at TIMESTAMPTZ NOT NULL,
          ended_at TIMESTAMPTZ,
          UNIQUE (game_id, round, player, phase)
        );

        CREATE TABLE unit_states (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL,
          list_version_id BIGINT NOT NULL,
          list_unit_id BIGINT NOT NULL,
          round SMALLINT NOT NULL CHECK (round BETWEEN 1 AND 10),
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          moved TEXT NOT NULL DEFAULT 'none' CHECK (moved IN ('none','normal','advanced','fell_back','remained')),
          shot BOOLEAN NOT NULL DEFAULT false,
          charged BOOLEAN NOT NULL DEFAULT false,
          fought BOOLEAN NOT NULL DEFAULT false,
          engaged BOOLEAN NOT NULL DEFAULT false,
          on_action BOOLEAN NOT NULL DEFAULT false,
          action_name TEXT CHECK (length(action_name) <= 200),
          battle_shocked BOOLEAN NOT NULL DEFAULT false,
          below_half BOOLEAN NOT NULL DEFAULT false,
          destroyed BOOLEAN NOT NULL DEFAULT false,
          in_reserves BOOLEAN NOT NULL DEFAULT false,
          overrides JSONB NOT NULL DEFAULT '[]',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (game_id, list_unit_id, round, player),
          FOREIGN KEY (game_id, list_version_id) REFERENCES games (id, list_version_id) ON DELETE CASCADE,
          FOREIGN KEY (list_unit_id, list_version_id) REFERENCES list_units (id, list_version_id)
        );
        CREATE INDEX ix_unit_states_game ON unit_states (game_id, list_version_id);
        CREATE INDEX ix_unit_states_unit ON unit_states (list_unit_id, list_version_id);

        CREATE TABLE stratagem_uses (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          ability_id BIGINT REFERENCES abilities(id) ON DELETE SET NULL,
          stratagem_name TEXT NOT NULL,
          round SMALLINT NOT NULL,
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          phase TEXT NOT NULL,
          cp_spent SMALLINT NOT NULL CHECK (cp_spent BETWEEN 0 AND 5),
          target_list_unit_id BIGINT REFERENCES list_units(id),
          limit_overridden BOOLEAN NOT NULL DEFAULT false,
          created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_strat_uses_game ON stratagem_uses (game_id, round, player, phase);
        CREATE INDEX ix_strat_uses_ability ON stratagem_uses (ability_id);
        CREATE INDEX ix_strat_uses_target ON stratagem_uses (target_list_unit_id);

        CREATE TABLE cp_ledger (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          round SMALLINT NOT NULL,
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          phase TEXT NOT NULL,
          delta SMALLINT NOT NULL CHECK (delta BETWEEN -10 AND 10),
          reason TEXT NOT NULL CHECK (reason IN ('command_phase','stratagem','ability','manual')),
          stratagem_use_id UUID REFERENCES stratagem_uses(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_cp_ledger_game ON cp_ledger (game_id);
        CREATE INDEX ix_cp_ledger_strat ON cp_ledger (stratagem_use_id);

        CREATE TABLE objective_control (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          round SMALLINT NOT NULL,
          player_turn TEXT NOT NULL CHECK (player_turn IN ('me','opponent')),
          objective_label TEXT NOT NULL CHECK (length(objective_label) <= 50),
          controller TEXT NOT NULL CHECK (controller IN ('me','opponent','contested','none')),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (game_id, round, player_turn, objective_label)
        );

        CREATE TABLE game_scores (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          round SMALLINT NOT NULL,
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          kind TEXT NOT NULL CHECK (kind IN ('primary','secondary','other')),
          label TEXT NOT NULL CHECK (length(label) <= 100),
          vp SMALLINT NOT NULL CHECK (vp BETWEEN -50 AND 50),
          created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_game_scores_game ON game_scores (game_id);

        CREATE TABLE faction_round_states (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          round SMALLINT NOT NULL,
          player TEXT NOT NULL CHECK (player IN ('me','opponent')),
          state_key TEXT NOT NULL CHECK (state_key IN ('shadow_of_chaos')),
          objectives_controlled SMALLINT CHECK (objectives_controlled BETWEEN 0 AND 20),
          whole_board BOOLEAN,
          value JSONB NOT NULL DEFAULT '{}',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (game_id, round, player, state_key)
        );

        CREATE TRIGGER trg_games_updated BEFORE UPDATE ON games
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_unit_states_updated BEFORE UPDATE ON unit_states
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_objective_control_updated BEFORE UPDATE ON objective_control
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_faction_round_states_updated BEFORE UPDATE ON faction_round_states
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS faction_round_states, game_scores, objective_control, cp_ledger,
          stratagem_uses, unit_states, game_turns, game_events, games CASCADE;
        """
    )
