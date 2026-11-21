-- Migration 003: Idempotently align pre-existing Neon tables with the unified schema
-- without dropping tables or deleting any existing user records.

-- 1. route_plans alignment
ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS map_provider VARCHAR(40) NOT NULL DEFAULT 'simulated';

UPDATE route_plans SET recommended_algorithm = 'A*' WHERE recommended_algorithm = 'ASTAR';
UPDATE route_plans SET recommended_algorithm = 'GENETIC_ALGORITHM' WHERE recommended_algorithm = 'GA';
UPDATE route_plans SET selected_algorithm = 'A*' WHERE selected_algorithm = 'ASTAR';
UPDATE route_plans SET selected_algorithm = 'GENETIC_ALGORITHM' WHERE selected_algorithm = 'GA';

ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_recommended_algorithm_check;
ALTER TABLE route_plans ADD CONSTRAINT route_plans_recommended_algorithm_check
  CHECK (recommended_algorithm IS NULL OR recommended_algorithm IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM'));

ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_selected_algorithm_check;
ALTER TABLE route_plans ADD CONSTRAINT route_plans_selected_algorithm_check
  CHECK (selected_algorithm IS NULL OR selected_algorithm IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM'));

-- 2. route_stops alignment
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS stop_name VARCHAR(180) NOT NULL DEFAULT '';
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS travel_from_previous_minutes INTEGER;
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS distance_from_previous_km DOUBLE PRECISION;
ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS visit_duration_minutes INTEGER NOT NULL DEFAULT 0;

-- 3. distributor_clusters alignment
ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS route_plan_id UUID REFERENCES route_plans(id) ON DELETE CASCADE;
ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS cluster_number INTEGER;
ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS centroid_latitude DOUBLE PRECISION;
ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS centroid_longitude DOUBLE PRECISION;
ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS distributor_ids UUID[] NOT NULL DEFAULT '{}';

-- 4. schedule_entries alignment
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS distributor_name VARCHAR(180) NOT NULL DEFAULT '';
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS scheduled_start TIMESTAMPTZ;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS scheduled_end TIMESTAMPTZ;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS visit_duration_minutes INTEGER NOT NULL DEFAULT 30;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 3;
ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS cluster_number INTEGER;

-- 5. algorithm_runs alignment
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed';
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS route_order UUID[] NOT NULL DEFAULT '{}';
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS route_names JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS total_distance_km DOUBLE PRECISION;
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS parameters JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS result_details JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS error_message TEXT;

UPDATE algorithm_runs SET algorithm_name = 'A*' WHERE algorithm_name = 'ASTAR';
UPDATE algorithm_runs SET algorithm_name = 'GENETIC_ALGORITHM' WHERE algorithm_name = 'GA';

ALTER TABLE algorithm_runs DROP CONSTRAINT IF EXISTS algorithm_runs_algorithm_name_check;
ALTER TABLE algorithm_runs ADD CONSTRAINT algorithm_runs_algorithm_name_check
  CHECK (algorithm_name IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM'));

-- 6. api_request_logs alignment
ALTER TABLE api_request_logs ADD COLUMN IF NOT EXISTS provider VARCHAR(60) NOT NULL DEFAULT 'internal_api';
ALTER TABLE api_request_logs ADD COLUMN IF NOT EXISTS endpoint VARCHAR(160) NOT NULL DEFAULT '';
ALTER TABLE api_request_logs ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE api_request_logs ADD COLUMN IF NOT EXISTS error_message TEXT;

-- 7. Relax legacy NOT NULL constraints & backfill where applicable
DO $$
DECLARE
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND is_nullable = 'NO'
      AND (
        (table_name = 'route_stops' AND column_name IN ('stop_type', 'leg_distance_km', 'leg_duration_minutes', 'notes'))
        OR (table_name = 'distributor_clusters' AND column_name IN ('run_group_id', 'distributor_id', 'cluster_index', 'k_value', 'centroid_lat', 'centroid_lng', 'iterations', 'converged', 'seed', 'is_demo'))
        OR (table_name = 'schedule_entries' AND column_name IN ('schedule_run_id', 'schedule_date', 'start_time', 'end_time', 'duration_minutes', 'buffer_minutes', 'priority_at_run', 'distributor_id', 'constraint_notes', 'is_demo'))
        OR (table_name = 'algorithm_runs' AND column_name IN ('is_informed', 'objective_description', 'route_order_json', 'estimated_distance_km', 'edge_count', 'is_recommended', 'metadata_json'))
        OR (table_name = 'api_request_logs' AND column_name IN ('method', 'path', 'status_code', 'duration_ms'))
      )
  LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN %I DROP NOT NULL', rec.table_name, rec.column_name);
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'algorithm_runs' AND column_name = 'estimated_distance_km'
  ) THEN
    EXECUTE 'UPDATE algorithm_runs SET total_distance_km = estimated_distance_km WHERE total_distance_km IS NULL AND estimated_distance_km IS NOT NULL';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_schedule_entries_plan_start ON schedule_entries(route_plan_id, scheduled_start);
