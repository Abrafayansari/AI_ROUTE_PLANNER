"""Non-destructive schema baseline aligned with Neon PostgreSQL tables.

Revision ID: 001_align_existing_schema
Revises:
Create Date: 2026-11-20 00:00:00.000000
"""
from alembic import op

revision = "001_align_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Non-destructive: creates only missing tables/columns without dropping existing Neon data
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS field_officers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(140) NOT NULL,
            email VARCHAR(180) UNIQUE,
            phone VARCHAR(30),
            territory VARCHAR(140),
            work_start_time VARCHAR(10) NOT NULL DEFAULT '09:00',
            work_end_time VARCHAR(10) NOT NULL DEFAULT '17:00',
            max_daily_visits INTEGER NOT NULL DEFAULT 10,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_demo BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS office_locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(160) NOT NULL,
            address VARCHAR(255) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT TRUE,
            is_demo BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS distributors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(180) NOT NULL,
            contact_person VARCHAR(140) NOT NULL,
            phone VARCHAR(30) NOT NULL,
            email VARCHAR(180),
            address VARCHAR(255) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            priority SMALLINT NOT NULL DEFAULT 3,
            visit_duration_minutes INTEGER NOT NULL DEFAULT 30,
            opening_time VARCHAR(10) NOT NULL DEFAULT '08:00',
            closing_time VARCHAR(10) NOT NULL DEFAULT '18:00',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT NOT NULL DEFAULT '',
            is_demo BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS route_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(180) NOT NULL,
            plan_date DATE NOT NULL,
            officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL,
            office_id UUID NOT NULL REFERENCES office_locations(id) ON DELETE RESTRICT,
            travel_mode VARCHAR(40) NOT NULL DEFAULT 'simulated_vehicle',
            return_to_office BOOLEAN NOT NULL DEFAULT TRUE,
            recommended_algorithm VARCHAR(50),
            selected_algorithm VARCHAR(50),
            total_distance_km DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_duration_minutes INTEGER NOT NULL DEFAULT 0,
            distance_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.25,
            graph_seed INTEGER NOT NULL DEFAULT 42,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            map_provider VARCHAR(40) NOT NULL DEFAULT 'simulated',
            notes TEXT,
            is_demo BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade():
    # Intentionally non-destructive: do not drop production Neon tables.
    pass
