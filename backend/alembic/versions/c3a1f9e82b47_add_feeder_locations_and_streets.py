"""add_feeder_locations_and_streets

Revision ID: c3a1f9e82b47
Revises: b465733dae8f
Create Date: 2026-04-06 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision: str = 'c3a1f9e82b47'
down_revision: Union[str, None] = 'b465733dae8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add composite unique constraint to feeders
    op.create_unique_constraint("uq_feeder_name_disco_code", "feeders", ["name", "disco_code"])

    # Create feeder_locations table
    op.create_table(
        "feeder_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("feeder_name", sa.String, nullable=False),
        sa.Column("disco_code", sa.String(10), nullable=False),
        sa.Column("location_description", sa.String, nullable=True),
        sa.ForeignKeyConstraint(
            ["feeder_name", "disco_code"],
            ["feeders.name", "feeders.disco_code"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_feeder_locations_disco", "feeder_locations", ["disco_code"])
    op.create_index("idx_feeder_locations_feeder", "feeder_locations", ["feeder_name", "disco_code"])

    # Create feeder_streets table
    op.create_table(
        "feeder_streets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("feeder_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("street_name", sa.String, nullable=False),
        sa.Column("formatted_address", sa.String, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column(
            "bounds",
            geoalchemy2.types.Geometry(geometry_type="POLYGON", srid=4326),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["feeder_location_id"],
            ["feeder_locations.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_feeder_streets_location", "feeder_streets", ["feeder_location_id"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feeder_streets_bounds ON feeder_streets USING GIST (bounds)"
    )


def downgrade() -> None:
    op.drop_table("feeder_streets")
    op.drop_table("feeder_locations")
    op.drop_constraint("uq_feeder_name_disco_code", "feeders", type_="unique")
