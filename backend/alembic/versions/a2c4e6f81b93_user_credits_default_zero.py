"""user_credits_default_zero

Revision ID: a2c4e6f81b93
Revises: f1a3b8c92d04
Create Date: 2026-04-10 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2c4e6f81b93'
down_revision: Union[str, None] = 'f1a3b8c92d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        server_default="0",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        server_default="1",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
