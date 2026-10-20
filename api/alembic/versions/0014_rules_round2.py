"""phases end_of_round, event types, restriction_keys, choice_scope, source_ref

Revision ID: 0014_rules_round2
Revises: 0013_shadow_phase
Create Date: 2026-10-20
"""

from alembic import op

revision = "0014_rules_round2"
down_revision = "0013_shadow_phase"
branch_labels = None
depends_on = None

_PHASES = (
    "'round_start','command','battle_shock','movement','shooting','charge',"
    "'fight','end_of_turn','end_of_round'"
)
_EFFECT_PHASES = (
    "'deployment','round_start','command','battle_shock','movement','shooting',"
    "'charge','fight','end_of_turn','end_of_round','any'"
)
_OLD_PHASES = (
    "'round_start','command','battle_shock','movement','shooting','charge',"
    "'fight','end_of_turn'"
)
_OLD_EFFECT_PHASES = (
    "'deployment','round_start','command','battle_shock','movement','shooting',"
    "'charge','fight','end_of_turn','any'"
)
_RESTRICTIONS = (
    "'shoot_after_advance','shoot_after_fall_back','charge_after_advance',"
    "'charge_after_fall_back','shoot_on_action','shoot_engaged','fight_again',"
    "'overwatch','heroic_intervention','rapid_ingress','reactive_move',"
    "'action_after_advance','action_after_fall_back'"
)
_OLD_RESTRICTIONS = (
    "'shoot_after_advance','shoot_after_fall_back','charge_after_advance',"
    "'charge_after_fall_back','shoot_on_action','shoot_engaged','fight_again'"
)
_EVENT_TYPES = (
    "'game_started','phase_advanced','unit_state_set','cp_changed','stratagem_used',"
    "'objective_set','vp_scored','shadow_set','battleshock_result','effect_chosen',"
    "'undo','game_ended','game_settings_set','checklist_set'"
)
_OLD_EVENT_TYPES = (
    "'game_started','phase_advanced','unit_state_set','cp_changed','stratagem_used',"
    "'objective_set','vp_scored','shadow_set','battleshock_result','effect_chosen',"
    "'undo','game_ended'"
)


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

        ALTER TABLE game_events DROP CONSTRAINT IF EXISTS game_events_type_check;
        ALTER TABLE game_events ADD CONSTRAINT game_events_type_check
          CHECK (type IN ({_EVENT_TYPES}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_restriction_key_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_restriction_key_check
          CHECK (restriction_key IS NULL OR restriction_key IN ({_RESTRICTIONS}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_choice_scope_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_choice_scope_check
          CHECK (choice_scope IN ('turn','round','battle','until_own_command'));

        ALTER TABLE target_profiles
          ADD COLUMN IF NOT EXISTS source_ref TEXT;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM games WHERE current_phase = 'end_of_round') THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: games com end_of_round';
          END IF;
          IF EXISTS (SELECT 1 FROM game_turns WHERE phase = 'end_of_round') THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: game_turns com end_of_round';
          END IF;
          IF EXISTS (SELECT 1 FROM rule_effects WHERE phase = 'end_of_round') THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: rule_effects com end_of_round';
          END IF;
          IF EXISTS (
            SELECT 1 FROM game_events
            WHERE type IN ('game_settings_set','checklist_set')
          ) THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: eventos com tipos novos';
          END IF;
          IF EXISTS (
            SELECT 1 FROM rule_effects
            WHERE restriction_key IN (
              'overwatch','heroic_intervention','rapid_ingress','reactive_move',
              'action_after_advance','action_after_fall_back'
            )
          ) THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: restriction_key novos';
          END IF;
          IF EXISTS (
            SELECT 1 FROM rule_effects WHERE choice_scope = 'until_own_command'
          ) THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: choice_scope until_own_command';
          END IF;
          IF EXISTS (
            SELECT 1 FROM target_profiles WHERE source_ref IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'downgrade 0014 recusado: target_profiles.source_ref';
          END IF;
        END $$;

        ALTER TABLE target_profiles DROP COLUMN IF EXISTS source_ref;

        ALTER TABLE games DROP CONSTRAINT IF EXISTS games_current_phase_check;
        ALTER TABLE games ADD CONSTRAINT games_current_phase_check
          CHECK (current_phase IN ({_OLD_PHASES}));

        ALTER TABLE game_turns DROP CONSTRAINT IF EXISTS game_turns_phase_check;
        ALTER TABLE game_turns ADD CONSTRAINT game_turns_phase_check
          CHECK (phase IN ({_OLD_PHASES}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_phase_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_phase_check
          CHECK (phase IN ({_OLD_EFFECT_PHASES}));

        ALTER TABLE game_events DROP CONSTRAINT IF EXISTS game_events_type_check;
        ALTER TABLE game_events ADD CONSTRAINT game_events_type_check
          CHECK (type IN ({_OLD_EVENT_TYPES}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_restriction_key_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_restriction_key_check
          CHECK (restriction_key IS NULL OR restriction_key IN ({_OLD_RESTRICTIONS}));

        ALTER TABLE rule_effects DROP CONSTRAINT IF EXISTS rule_effects_choice_scope_check;
        ALTER TABLE rule_effects ADD CONSTRAINT rule_effects_choice_scope_check
          CHECK (choice_scope IN ('turn','round','battle'));
        """
    )
