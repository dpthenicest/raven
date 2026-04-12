"""add_band_to_feeder_locations

Revision ID: e4b2c9d71a38
Revises: d7f2a1c84e91
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e4b2c9d71a38'
down_revision: Union[str, None] = 'd7f2a1c84e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "feeder_locations",
        sa.Column("band", sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feeder_locations", "band")
