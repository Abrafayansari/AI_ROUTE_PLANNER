"""Add visit_delay_predictions table for Bayesian Network delay prediction.

Revision ID: 002_add_visit_delay_predictions
Revises: 001_align_existing_schema
Create Date: 2026-11-21 00:00:00.000000
"""
from alembic import op

revision = "002_add_visit_delay_predictions"
down_revision = "001_align_existing_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS visit_delay_predictions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID REFERENCES route_plans(id) ON DELETE CASCADE,
            distributor_id UUID REFERENCES distributors(id) ON DELETE SET NULL,
            distributor_name VARCHAR(180) NOT NULL,
            stop_order INTEGER,
            distance_km DOUBLE PRECISION,
            distance_category VARCHAR(20) NOT NULL,
            visit_duration_minutes INTEGER,
            visit_duration_category VARCHAR(20) NOT NULL,
            time_slot VARCHAR(20) NOT NULL,
            priority_category VARCHAR(20) NOT NULL,
            probability_low DOUBLE PRECISION NOT NULL,
            probability_medium DOUBLE PRECISION NOT NULL,
            probability_high DOUBLE PRECISION NOT NULL,
            predicted_risk VARCHAR(20) NOT NULL,
            recommended_buffer_minutes INTEGER NOT NULL DEFAULT 0,
            recommendation_note TEXT,
            model_version VARCHAR(40) NOT NULL DEFAULT '1.0.0-illustrative',
            model_status VARCHAR(40) NOT NULL DEFAULT 'illustrative_baseline',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_plan ON visit_delay_predictions(route_plan_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_dist ON visit_delay_predictions(distributor_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_created ON visit_delay_predictions(created_at);")


def downgrade():
    # Intentionally non-destructive
    pass
