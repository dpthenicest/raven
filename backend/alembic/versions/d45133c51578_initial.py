"""initial

Revision ID: d45133c51578
Revises: 
Create Date: 2026-03-25 10:32:30.377831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = 'd45133c51578'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute("""
        CREATE TABLE IF NOT EXISTS discos (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL,
            code VARCHAR(10) UNIQUE NOT NULL,
            path VARCHAR
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            email VARCHAR UNIQUE NOT NULL,
            oauth_id VARCHAR UNIQUE,
            credits INTEGER NOT NULL DEFAULT 1,
            role VARCHAR NOT NULL DEFAULT 'USER',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tariffband') THEN
                CREATE TYPE tariffband AS ENUM ('A','B','C','D','E');
            END IF;
        END $$
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'searchsource') THEN
                CREATE TYPE searchsource AS ENUM ('LIST','MAP');
            END IF;
        END $$
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transactionstatus') THEN
                CREATE TYPE transactionstatus AS ENUM ('PENDING','SUCCESS','FAILED');
            END IF;
        END $$
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                CREATE TYPE userrole AS ENUM ('USER','ADMIN');
            END IF;
        END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS feeders (
            id UUID PRIMARY KEY,
            disco_id UUID NOT NULL REFERENCES discos(id),
            name VARCHAR NOT NULL,
            tariff_band tariffband NOT NULL,
            formatted_address VARCHAR,
            aliases JSONB NOT NULL DEFAULT '[]',
            state VARCHAR,
            longitude FLOAT,
            latitude FLOAT,
            bounds geometry(POLYGON, 4326),
            search_vector TSVECTOR,
            cap_kwh FLOAT,
            confidence_score FLOAT NOT NULL DEFAULT 1.0,
            last_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_feeders_bounds ON feeders USING GIST (bounds)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feeders_name ON feeders (name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feeders_search ON feeders USING GIN (search_vector)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            txn_ref VARCHAR UNIQUE NOT NULL,
            amount FLOAT NOT NULL,
            status transactionstatus NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ratings_reviews (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            feeder_id UUID NOT NULL REFERENCES feeders(id),
            stars INTEGER NOT NULL,
            actual_hours FLOAT NOT NULL,
            review VARCHAR,
            questions JSONB NOT NULL DEFAULT '{}',
            upvotes INTEGER NOT NULL DEFAULT 0,
            downvotes INTEGER NOT NULL DEFAULT 0,
            is_verified BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            feeder_id UUID REFERENCES feeders(id),
            lat FLOAT,
            lng FLOAT,
            found_band VARCHAR(1),
            device_type VARCHAR,
            search_source searchsource NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_searches_user_id ON searches (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS searches CASCADE")
    op.execute("DROP TABLE IF EXISTS ratings_reviews CASCADE")
    op.execute("DROP TABLE IF EXISTS transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS feeders CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS discos CASCADE")
    op.execute("DROP TYPE IF EXISTS tariffband")
    op.execute("DROP TYPE IF EXISTS searchsource")
    op.execute("DROP TYPE IF EXISTS transactionstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
