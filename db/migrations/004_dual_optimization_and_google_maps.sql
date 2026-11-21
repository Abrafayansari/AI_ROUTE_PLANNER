-- Migration 004: Additive schema updates for Dual Route Optimization (FASTEST_TIME vs SHORTEST_DISTANCE)
-- and Google Maps Routes API traffic-aware telemetry without touching existing Neon data.

ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS normal_duration_minutes INTEGER;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_delay_minutes INTEGER;
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;

ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_travel_mode_check;
ALTER TABLE route_plans ADD CONSTRAINT route_plans_travel_mode_check
  CHECK (travel_mode IN ('simulated_vehicle', 'simulated_walking', 'simulated_van', 'DRIVE', 'TWO_WHEELER', 'WALK'));

ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_optimization_objective_check;
ALTER TABLE route_plans ADD CONSTRAINT route_plans_optimization_objective_check
  CHECK (optimization_objective IN ('FASTEST_TIME', 'SHORTEST_DISTANCE'));

ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS static_travel_from_previous_minutes INTEGER;

ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;

ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS travel_from_previous_minutes INTEGER;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS distance_from_previous_km DOUBLE PRECISION;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) DEFAULT 'simulated_fallback';
