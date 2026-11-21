-- Migration 002: Add is_demo flag, deterministic graph seed/multiplier metadata, and indexes.
-- Non-destructive: uses ADD COLUMN IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.

ALTER TABLE field_officers ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE office_locations ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE distributors ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS distance_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.25;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS graph_seed INTEGER NOT NULL DEFAULT 42;

CREATE INDEX IF NOT EXISTS idx_distributors_active ON distributors(is_active);
CREATE INDEX IF NOT EXISTS idx_distributors_coordinates ON distributors(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_route_plans_date ON route_plans(plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_route_plans_officer ON route_plans(officer_id);
CREATE INDEX IF NOT EXISTS idx_route_stops_plan_order ON route_stops(route_plan_id, stop_order);
CREATE INDEX IF NOT EXISTS idx_algorithm_runs_plan ON algorithm_runs(route_plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_request_logs_created ON api_request_logs(created_at DESC);
