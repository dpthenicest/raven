"""add name to users

Revision ID: 2bf5a293340f
Revises: d45133c51578
Create Date: 2026-03-25 10:52:22.504391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2bf5a293340f'
down_revision: Union[str, None] = 'd45133c51578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'name')
