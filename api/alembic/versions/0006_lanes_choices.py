"""faixas da mesa e efeitos com escolha

Revision ID: 0006_lanes_choices
Revises: 0005_maps
Create Date: 2026-10-15
"""

from alembic import op

revision = "0006_lanes_choices"
down_revision = "0005_maps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE rule_effects
          ADD COLUMN choice_options JSONB NOT NULL DEFAULT '[]'
            CHECK (jsonb_typeof(choice_options) = 'array' AND jsonb_array_length(choice_options) <= 12),
          ADD COLUMN choice_count SMALLINT CHECK (choice_count BETWEEN 1 AND 6),
          ADD COLUMN choice_scope TEXT NOT NULL DEFAULT 'turn' CHECK (choice_scope IN ('turn','round','battle'));

        ALTER TABLE unit_states
          ADD COLUMN lane TEXT NOT NULL DEFAULT 'center' CHECK (lane IN ('left','center','right'));

        ALTER TABLE game_events DROP CONSTRAINT game_events_type_check;
        ALTER TABLE game_events ADD CONSTRAINT game_events_type_check CHECK (type IN (
          'game_started','phase_advanced','unit_state_set','cp_changed','stratagem_used','objective_set',
          'vp_scored','shadow_set','battleshock_result','effect_chosen','undo','game_ended'
        ));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM game_events WHERE type = 'effect_chosen') THEN
            RAISE EXCEPTION 'DB5: downgrade 0006 apagaria effect_chosen; restaure o snapshot (S3)';
          END IF;
        END $$;
        ALTER TABLE game_events DROP CONSTRAINT game_events_type_check;
        ALTER TABLE game_events ADD CONSTRAINT game_events_type_check CHECK (type IN (
          'game_started','phase_advanced','unit_state_set','cp_changed','stratagem_used','objective_set',
          'vp_scored','shadow_set','battleshock_result','undo','game_ended'
        ));
        ALTER TABLE unit_states DROP COLUMN IF EXISTS lane;
        ALTER TABLE rule_effects
          DROP COLUMN IF EXISTS choice_scope,
          DROP COLUMN IF EXISTS choice_count,
          DROP COLUMN IF EXISTS choice_options;
        """
    )
