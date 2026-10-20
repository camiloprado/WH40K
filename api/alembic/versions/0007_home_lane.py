"""faixa home na mesa

Revision ID: 0007_home_lane
Revises: 0006_lanes_choices
Create Date: 2026-10-15
"""

from alembic import op

revision = "0007_home_lane"
down_revision = "0006_lanes_choices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE unit_states DROP CONSTRAINT unit_states_lane_check;
        ALTER TABLE unit_states ADD CONSTRAINT unit_states_lane_check CHECK (lane IN ('left','center','right','home'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE unit_states SET lane = 'center' WHERE lane = 'home';
        ALTER TABLE unit_states DROP CONSTRAINT unit_states_lane_check;
        ALTER TABLE unit_states ADD CONSTRAINT unit_states_lane_check CHECK (lane IN ('left','center','right'));
        """
    )
