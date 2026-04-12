"""drop_feeder_location_fk_constraint

Revision ID: d7f2a1c84e91
Revises: c3a1f9e82b47
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'd7f2a1c84e91'
down_revision: Union[str, None] = 'c3a1f9e82b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the composite FK constraint so feeder_locations can store
    # all MYTO data regardless of whether the feeder exists in the feeders table
    op.drop_constraint(
        "feeder_locations_feeder_name_disco_code_fkey",
        "feeder_locations",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "feeder_locations_feeder_name_disco_code_fkey",
        "feeder_locations",
        "feeders",
        ["feeder_name", "disco_code"],
        ["name", "disco_code"],
        ondelete="CASCADE",
    )
