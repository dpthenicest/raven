"""add_unknown_tariff_band

Revision ID: b465733dae8f
Revises: 02314e4324a0
Create Date: 2026-03-26 18:52:22.613112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


revision: str = 'b465733dae8f'
down_revision: Union[str, None] = '02314e4324a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add '-' (UNKNOWN) value to tariffband enum
    op.execute("ALTER TYPE tariffband ADD VALUE IF NOT EXISTS '-'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values
    # This would require recreating the enum type
    pass
