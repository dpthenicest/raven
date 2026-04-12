"""widen_feeder_location_band_column

Revision ID: f1a3b8c92d04
Revises: e4b2c9d71a38
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1a3b8c92d04'
down_revision: Union[str, None] = 'e4b2c9d71a38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "feeder_locations",
        "band",
        type_=sa.String(10),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "feeder_locations",
        "band",
        type_=sa.String(5),
        existing_nullable=True,
    )
