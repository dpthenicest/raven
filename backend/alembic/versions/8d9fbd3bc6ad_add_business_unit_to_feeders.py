"""add business_unit to feeders

Revision ID: 8d9fbd3bc6ad
Revises: 2bf5a293340f
Create Date: 2026-03-25 11:43:48.646402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8d9fbd3bc6ad'
down_revision: Union[str, None] = '2bf5a293340f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('feeders', sa.Column('business_unit', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('feeders', 'business_unit')
