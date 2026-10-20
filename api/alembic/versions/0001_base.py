"""base + listas + sessoes

Revision ID: 0001_base
Revises:
Create Date: 2026-10-15
"""

from alembic import op

revision = "0001_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TABLE factions (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL UNIQUE CHECK (length(name) <= 200),
          short_name TEXT,
          accent_color CHAR(7) NOT NULL DEFAULT '#8A8A8A' CHECK (accent_color ~ '^#[0-9A-Fa-f]{6}$'),
          source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','import','bsdata')),
          source_ref TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE detachments (
          id BIGSERIAL PRIMARY KEY,
          faction_id BIGINT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          variant TEXT,
          notes TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE NULLS NOT DISTINCT (faction_id, name, variant)
        );
        CREATE INDEX ix_detachments_faction_id ON detachments (faction_id);

        CREATE TABLE datasheets (
          id BIGSERIAL PRIMARY KEY,
          faction_id BIGINT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          movement SMALLINT,
          toughness SMALLINT CHECK (toughness >= 1),
          save SMALLINT CHECK (save BETWEEN 2 AND 6),
          invuln SMALLINT CHECK (invuln BETWEEN 2 AND 6),
          wounds SMALLINT CHECK (wounds >= 1),
          leadership SMALLINT,
          oc SMALLINT,
          fnp SMALLINT CHECK (fnp BETWEEN 2 AND 6),
          keywords TEXT[] NOT NULL DEFAULT '{}',
          base_size_mm TEXT,
          is_character BOOLEAN NOT NULL DEFAULT false,
          allows_two_leaders BOOLEAN NOT NULL DEFAULT false,
          is_stub BOOLEAN NOT NULL DEFAULT true,
          source TEXT NOT NULL DEFAULT 'user',
          source_ref TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (faction_id, name),
          CHECK (cardinality(keywords) <= 50)
        );
        CREATE INDEX ix_datasheets_faction_id ON datasheets (faction_id);

        CREATE TABLE weapons (
          id BIGSERIAL PRIMARY KEY,
          datasheet_id BIGINT REFERENCES datasheets(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          kind TEXT NOT NULL DEFAULT 'unknown' CHECK (kind IN ('ranged','melee','wargear','unknown')),
          range_in SMALLINT,
          attacks TEXT CHECK (attacks IS NULL OR attacks ~ '^(\\d{1,2}|D3|D6|\\d?D[36](\\+\\d{1,2})?)$'),
          skill SMALLINT CHECK (skill BETWEEN 2 AND 6),
          strength SMALLINT CHECK (strength >= 1),
          ap SMALLINT CHECK (ap BETWEEN -6 AND 0),
          damage TEXT CHECK (damage IS NULL OR damage ~ '^(\\d{1,2}|D3|D6|\\d?D[36](\\+\\d{1,2})?)$'),
          keywords TEXT[] NOT NULL DEFAULT '{}',
          is_stub BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE NULLS NOT DISTINCT (datasheet_id, name),
          CHECK (cardinality(keywords) <= 50)
        );
        CREATE INDEX ix_weapons_datasheet_id ON weapons (datasheet_id);

        CREATE TABLE lists (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          faction_id BIGINT REFERENCES factions(id),
          current_version_id BIGINT,
          archived BOOLEAN NOT NULL DEFAULT false,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_lists_faction_id ON lists (faction_id);

        CREATE TABLE imports (
          id BIGSERIAL PRIMARY KEY,
          list_id BIGINT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
          raw_text TEXT NOT NULL CHECK (octet_length(raw_text) <= 204800),
          input_format TEXT NOT NULL CHECK (input_format IN ('nr_json','nr_text_simple','nr_text_wtc_compact','nr_text_wtc_full','nr_text_unknown')),
          parser_version TEXT NOT NULL,
          parse_hash CHAR(64) NOT NULL,
          generator TEXT,
          parsed_json JSONB NOT NULL,
          warnings JSONB NOT NULL DEFAULT '[]',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_imports_list_id ON imports (list_id);

        CREATE TABLE list_versions (
          id BIGSERIAL PRIMARY KEY,
          list_id BIGINT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
          version_no INT NOT NULL,
          import_id BIGINT REFERENCES imports(id) ON DELETE SET NULL,
          label TEXT,
          faction_name TEXT NOT NULL,
          detachment_names TEXT[] NOT NULL DEFAULT '{}',
          force_disposition TEXT,
          secondaries TEXT[] NOT NULL DEFAULT '{}',
          total_points_declared INT CHECK (total_points_declared BETWEEN 0 AND 100000),
          points_include_enhancement BOOLEAN,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (list_id, version_no),
          UNIQUE (id, list_id)
        );
        CREATE INDEX ix_list_versions_list_id ON list_versions (list_id);
        CREATE INDEX ix_list_versions_import_id ON list_versions (import_id);

        ALTER TABLE lists ADD CONSTRAINT fk_lists_current_version
          FOREIGN KEY (current_version_id, id) REFERENCES list_versions (id, list_id)
          DEFERRABLE INITIALLY DEFERRED;

        CREATE TABLE list_version_detachments (
          list_version_id BIGINT REFERENCES list_versions(id) ON DELETE CASCADE,
          detachment_id BIGINT REFERENCES detachments(id),
          PRIMARY KEY (list_version_id, detachment_id)
        );
        CREATE INDEX ix_lvd_detachment_id ON list_version_detachments (detachment_id);

        CREATE TABLE list_units (
          id BIGSERIAL PRIMARY KEY,
          list_version_id BIGINT NOT NULL REFERENCES list_versions(id) ON DELETE CASCADE,
          datasheet_name TEXT NOT NULL,
          datasheet_id BIGINT NOT NULL REFERENCES datasheets(id),
          export_ref TEXT,
          model_count SMALLINT NOT NULL CHECK (model_count BETWEEN 1 AND 200),
          points INT NOT NULL CHECK (points BETWEEN 0 AND 10000),
          enhancement_name TEXT,
          enhancement_points SMALLINT,
          is_warlord BOOLEAN NOT NULL DEFAULT false,
          sort_order SMALLINT NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (id, list_version_id)
        );
        CREATE INDEX ix_list_units_list_version_id ON list_units (list_version_id);
        CREATE INDEX ix_list_units_datasheet_id ON list_units (datasheet_id);
        CREATE UNIQUE INDEX uq_list_units_one_warlord ON list_units (list_version_id) WHERE is_warlord;
        CREATE UNIQUE INDEX uq_list_units_export_ref ON list_units (list_version_id, export_ref) WHERE export_ref IS NOT NULL;

        CREATE TABLE list_unit_models (
          id BIGSERIAL PRIMARY KEY,
          list_unit_id BIGINT NOT NULL REFERENCES list_units(id) ON DELETE CASCADE,
          model_name TEXT NOT NULL,
          count SMALLINT NOT NULL CHECK (count BETWEEN 1 AND 200),
          UNIQUE (id, list_unit_id)
        );
        CREATE INDEX ix_list_unit_models_list_unit_id ON list_unit_models (list_unit_id);

        CREATE TABLE list_unit_wargear (
          id BIGSERIAL PRIMARY KEY,
          list_unit_id BIGINT NOT NULL REFERENCES list_units(id) ON DELETE CASCADE,
          list_unit_model_id BIGINT,
          weapon_name TEXT NOT NULL,
          weapon_id BIGINT REFERENCES weapons(id) ON DELETE SET NULL,
          count SMALLINT NOT NULL DEFAULT 1 CHECK (count >= 1),
          FOREIGN KEY (list_unit_model_id, list_unit_id) REFERENCES list_unit_models (id, list_unit_id) ON DELETE CASCADE
        );
        CREATE INDEX ix_luw_list_unit_id ON list_unit_wargear (list_unit_id);
        CREATE INDEX ix_luw_model ON list_unit_wargear (list_unit_model_id, list_unit_id);
        CREATE INDEX ix_luw_weapon_id ON list_unit_wargear (weapon_id);

        CREATE TABLE attachments (
          id BIGSERIAL PRIMARY KEY,
          list_version_id BIGINT NOT NULL REFERENCES list_versions(id) ON DELETE CASCADE,
          leader_list_unit_id BIGINT NOT NULL,
          bodyguard_list_unit_id BIGINT NOT NULL,
          source TEXT NOT NULL DEFAULT 'import' CHECK (source IN ('import','user')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (leader_list_unit_id),
          FOREIGN KEY (leader_list_unit_id, list_version_id) REFERENCES list_units (id, list_version_id) ON DELETE CASCADE,
          FOREIGN KEY (bodyguard_list_unit_id, list_version_id) REFERENCES list_units (id, list_version_id) ON DELETE CASCADE,
          CHECK (leader_list_unit_id <> bodyguard_list_unit_id)
        );
        CREATE INDEX ix_attachments_list_version_id ON attachments (list_version_id);
        CREATE INDEX ix_attachments_bodyguard ON attachments (bodyguard_list_unit_id);

        CREATE TABLE sessions (
          id BIGSERIAL PRIMARY KEY,
          token_hash CHAR(64) NOT NULL UNIQUE,
          user_agent TEXT CHECK (length(user_agent) <= 300),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);

        CREATE TRIGGER trg_factions_updated BEFORE UPDATE ON factions
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_detachments_updated BEFORE UPDATE ON detachments
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_datasheets_updated BEFORE UPDATE ON datasheets
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_weapons_updated BEFORE UPDATE ON weapons
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_lists_updated BEFORE UPDATE ON lists
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_list_versions_updated BEFORE UPDATE ON list_versions
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        CREATE TRIGGER trg_attachments_updated BEFORE UPDATE ON attachments
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS sessions, attachments, list_unit_wargear, list_unit_models,
          list_units, list_version_detachments, list_versions, imports, lists,
          weapons, datasheets, detachments, factions CASCADE;
        DROP FUNCTION IF EXISTS set_updated_at();
        """
    )
