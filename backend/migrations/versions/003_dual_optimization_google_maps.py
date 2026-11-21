"""Add dual optimization objective, data_source, traffic timestamps, and polyline fields.

Revision ID: 003_dual_optimization_google_maps
Revises: 002_add_visit_delay_predictions
Create Date: 2026-11-21 12:00:00.000000
"""
from alembic import op

revision = "003_dual_optimization_google_maps"
down_revision = "002_add_visit_delay_predictions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';"
    )
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';"
    )
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;"
    )
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS normal_duration_minutes INTEGER;"
    )
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_delay_minutes INTEGER;"
    )
    op.execute(
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;"
    )
    op.execute(
        "ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_travel_mode_check;"
    )
    op.execute(
        """
        ALTER TABLE route_plans ADD CONSTRAINT route_plans_travel_mode_check
        CHECK (travel_mode IN ('simulated_vehicle', 'simulated_walking', 'simulated_van', 'DRIVE', 'TWO_WHEELER', 'WALK'));
        """
    )
    op.execute(
        "ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_optimization_objective_check;"
    )
    op.execute(
        """
        ALTER TABLE route_plans ADD CONSTRAINT route_plans_optimization_objective_check
        CHECK (optimization_objective IN ('FASTEST_TIME', 'SHORTEST_DISTANCE'));
        """
    )
    op.execute(
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS static_travel_from_previous_minutes INTEGER;"
    )
    op.execute(
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';"
    )
    op.execute(
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';"
    )
    op.execute(
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;"
    )
    op.execute(
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;"
    )
    op.execute(
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL;"
    )
    op.execute(
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS travel_from_previous_minutes INTEGER;"
    )
    op.execute(
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS distance_from_previous_km DOUBLE PRECISION;"
    )
    op.execute(
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) DEFAULT 'simulated_fallback';"
    )


def downgrade():
    # Intentionally non-destructive
    pass
