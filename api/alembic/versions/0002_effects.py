"""efeitos e colinha

Revision ID: 0002_effects
Revises: 0001_base
Create Date: 2026-10-15
"""

from alembic import op

revision = "0002_effects"
down_revision = "0001_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE abilities (
          id BIGSERIAL PRIMARY KEY,
          kind TEXT NOT NULL CHECK (kind IN ('core','faction','detachment','unit','leader','stratagem','enhancement','general')),
          faction_id BIGINT REFERENCES factions(id) ON DELETE CASCADE,
          datasheet_id BIGINT REFERENCES datasheets(id) ON DELETE CASCADE,
          detachment_id BIGINT REFERENCES detachments(id) ON DELETE CASCADE,
          name TEXT NOT NULL CHECK (length(name) <= 200),
          cp_cost SMALLINT CHECK (cp_cost BETWEEN 0 AND 5),
          use_limit TEXT CHECK (use_limit IN ('per_phase','per_turn','per_round','per_battle','none')),
          usable_turn TEXT CHECK (usable_turn IN ('own','opponent','either')),
          summary_user TEXT CHECK (length(summary_user) <= 4000),
          is_hypothesis BOOLEAN NOT NULL DEFAULT false,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE NULLS NOT DISTINCT (kind, faction_id, datasheet_id, detachment_id, name),
          CHECK (num_nonnulls(faction_id, datasheet_id, detachment_id) <= 1),
          CHECK (
            (kind IN ('core','general') AND num_nonnulls(faction_id, datasheet_id, detachment_id) = 0) OR
            (kind = 'faction' AND faction_id IS NOT NULL) OR
            (kind IN ('unit','leader') AND datasheet_id IS NOT NULL) OR
            (kind IN ('detachment','stratagem','enhancement') AND detachment_id IS NOT NULL)
          )
        );
        CREATE INDEX ix_abilities_faction_id ON abilities (faction_id);
        CREATE INDEX ix_abilities_datasheet_id ON abilities (datasheet_id);
        CREATE INDEX ix_abilities_detachment_id ON abilities (detachment_id);

        CREATE TABLE enhancements (
          id BIGSERIAL PRIMARY KEY,
          detachment_id BIGINT REFERENCES detachments(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          points SMALLINT CHECK (points >= 0),
          restrictions TEXT,
          ability_id BIGINT REFERENCES abilities(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE NULLS NOT DISTINCT (detachment_id, name)
        );
        CREATE INDEX ix_enhancements_ability_id ON enhancements (ability_id);
        CREATE INDEX ix_enhancements_detachment_id ON enhancements (detachment_id);

        ALTER TABLE list_units
          ADD COLUMN enhancement_id BIGINT REFERENCES enhancements(id) ON DELETE SET NULL;
        CREATE INDEX ix_list_units_enhancement_id ON list_units (enhancement_id);

        CREATE TABLE rule_effects (
          id BIGSERIAL PRIMARY KEY,
          ability_id BIGINT NOT NULL REFERENCES abilities(id) ON DELETE CASCADE,
          phase TEXT NOT NULL CHECK (phase IN ('deployment','command','battle_shock','movement','shooting','charge','fight','end_of_turn','any')),
          turn_owner TEXT NOT NULL DEFAULT 'own' CHECK (turn_owner IN ('own','opponent','both')),
          timing TEXT NOT NULL DEFAULT 'during' CHECK (timing IN ('start','during','end')),
          effect_kind TEXT NOT NULL DEFAULT 'reminder' CHECK (effect_kind IN ('reminder','allow','deny','prompt','stratagem')),
          restriction_key TEXT CHECK (restriction_key IN ('shoot_after_advance','shoot_after_fall_back','charge_after_advance','charge_after_fall_back','shoot_on_action','shoot_engaged','fight_again')),
          condition_json JSONB NOT NULL DEFAULT '{}',
          owner_label TEXT NOT NULL CHECK (length(owner_label) <= 200),
          effect_text TEXT NOT NULL CHECK (length(effect_text) <= 4000),
          range_in SMALLINT,
          sort_order SMALLINT NOT NULL DEFAULT 0,
          is_hypothesis BOOLEAN NOT NULL DEFAULT false,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (effect_kind NOT IN ('allow','deny') OR restriction_key IS NOT NULL)
        );
        CREATE INDEX ix_rule_effects_ability_id ON rule_effects (ability_id);

        CREATE TRIGGER trg_abilities_updated BEFORE UPDATE ON abilities
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_enhancements_updated BEFORE UPDATE ON enhancements
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_rule_effects_updated BEFORE UPDATE ON rule_effects
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE list_units DROP COLUMN IF EXISTS enhancement_id;
        DROP TABLE IF EXISTS rule_effects, enhancements, abilities CASCADE;
        """
    )
