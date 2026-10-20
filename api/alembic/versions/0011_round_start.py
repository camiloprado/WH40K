"""fase de início da battle round, antes da Command

Revision ID: 0011_round_start
Revises: 0010_ability_import
Create Date: 2026-10-15
"""

from alembic import op

revision = "0011_round_start"
down_revision = "0010_ability_import"
branch_labels = None
depends_on = None

_PHASES = "'round_start','command','battle_shock','movement','shooting','charge','fight','end_of_turn'"
_EFFECT_PHASES = "'deployment','round_start','command','battle_shock','movement','shooting','charge','fight','end_of_turn','any'"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE games DROP CONSTRAINT IF EXISTS games_current_phase_check;
        ALTER TABLE games ADD CONSTRAINT games_current_phase_check
          CHECK (current_phase IN ({_PHASES}));

        ALTER TABLE game_turns DROP CONSTRAINT IF EXISTS game_turns_phase_check;
        ALTER TABLE game_turns ADD CONSTRAINT game_turns_phase_check
          CHECK (phase IN ({_PHASES}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_phase_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_phase_check
          CHECK (phase IN ({_EFFECT_PHASES}));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM rule_effects WHERE phase = 'round_start') THEN
            RAISE EXCEPTION 'DB5: downgrade 0011 apagaria rule_effects round_start; restaure o snapshot (S3)';
          END IF;
        END $$;
        UPDATE games SET current_phase = 'command' WHERE current_phase = 'round_start';
        UPDATE game_turns SET phase = 'command' WHERE phase = 'round_start';
        ALTER TABLE games DROP CONSTRAINT IF EXISTS games_current_phase_check;
        ALTER TABLE games ADD CONSTRAINT games_current_phase_check
          CHECK (current_phase IN ('command','battle_shock','movement','shooting','charge','fight','end_of_turn'));
        ALTER TABLE game_turns DROP CONSTRAINT IF EXISTS game_turns_phase_check;
        ALTER TABLE game_turns ADD CONSTRAINT game_turns_phase_check
          CHECK (phase IN ('command','battle_shock','movement','shooting','charge','fight','end_of_turn'));
        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_phase_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_phase_check
          CHECK (phase IN ('deployment','command','battle_shock','movement','shooting','charge','fight','end_of_turn','any'));
        """
    )
