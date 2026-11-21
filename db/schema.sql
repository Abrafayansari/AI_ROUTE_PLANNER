-- Smart Route Planner for Sales Field Officers
-- Complete Neon PostgreSQL Schema (Aligned with supplied schema.sql)

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Field Officers (Week 2: Intelligent Agent Profile)
CREATE TABLE IF NOT EXISTS field_officers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(140) NOT NULL,
    email VARCHAR(180) UNIQUE,
    phone VARCHAR(30),
    territory VARCHAR(140),
    work_start_time VARCHAR(10) NOT NULL DEFAULT '09:00',
    work_end_time VARCHAR(10) NOT NULL DEFAULT '17:00',
    max_daily_visits INTEGER NOT NULL DEFAULT 10 CHECK (max_daily_visits > 0 AND max_daily_visits <= 50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Office / Base Locations
CREATE TABLE IF NOT EXISTS office_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(160) NOT NULL,
    address VARCHAR(255) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Distributors / Customer Locations
CREATE TABLE IF NOT EXISTS distributors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(180) NOT NULL,
    contact_person VARCHAR(140) NOT NULL,
    phone VARCHAR(30) NOT NULL CHECK (char_length(phone) >= 7 AND char_length(phone) <= 25),
    email VARCHAR(180),
    address VARCHAR(255) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    priority SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    visit_duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (visit_duration_minutes >= 5 AND visit_duration_minutes <= 480),
    opening_time VARCHAR(10) NOT NULL DEFAULT '08:00',
    closing_time VARCHAR(10) NOT NULL DEFAULT '18:00',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT NOT NULL DEFAULT '',
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Route Plans
CREATE TABLE IF NOT EXISTS route_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(180) NOT NULL,
    plan_date DATE NOT NULL,
    officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL,
    office_id UUID NOT NULL REFERENCES office_locations(id) ON DELETE RESTRICT,
    travel_mode VARCHAR(40) NOT NULL DEFAULT 'simulated_vehicle'
        CHECK (travel_mode IN ('simulated_vehicle', 'simulated_walking', 'simulated_van', 'DRIVE', 'TWO_WHEELER', 'WALK')),
    optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME'
        CHECK (optimization_objective IN ('FASTEST_TIME', 'SHORTEST_DISTANCE')),
    return_to_office BOOLEAN NOT NULL DEFAULT TRUE,
    recommended_algorithm VARCHAR(50)
        CHECK (recommended_algorithm IS NULL OR recommended_algorithm IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM')),
    selected_algorithm VARCHAR(50)
        CHECK (selected_algorithm IS NULL OR selected_algorithm IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM')),
    total_distance_km DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (total_distance_km >= 0),
    total_duration_minutes INTEGER NOT NULL DEFAULT 0 CHECK (total_duration_minutes >= 0),
    normal_duration_minutes INTEGER CHECK (normal_duration_minutes IS NULL OR normal_duration_minutes >= 0),
    traffic_delay_minutes INTEGER CHECK (traffic_delay_minutes IS NULL OR traffic_delay_minutes >= 0),
    distance_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (distance_multiplier >= 1.0 AND distance_multiplier <= 3.0),
    graph_seed INTEGER NOT NULL DEFAULT 42,
    status VARCHAR(30) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'optimized', 'scheduled', 'in_progress', 'completed')),
    map_provider VARCHAR(40) NOT NULL DEFAULT 'simulated',
    data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback',
    traffic_calculated_at TIMESTAMPTZ,
    encoded_polyline TEXT,
    notes TEXT DEFAULT '',
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Route Stops (1-indexed stop_order)
CREATE TABLE IF NOT EXISTS route_stops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
    distributor_id UUID REFERENCES distributors(id) ON DELETE SET NULL,
    stop_order INTEGER NOT NULL CHECK (stop_order > 0),
    stop_name VARCHAR(180) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    estimated_arrival TIMESTAMPTZ,
    estimated_departure TIMESTAMPTZ,
    travel_from_previous_minutes INTEGER CHECK (travel_from_previous_minutes IS NULL OR travel_from_previous_minutes >= 0),
    static_travel_from_previous_minutes INTEGER CHECK (static_travel_from_previous_minutes IS NULL OR static_travel_from_previous_minutes >= 0),
    distance_from_previous_km DOUBLE PRECISION CHECK (distance_from_previous_km IS NULL OR distance_from_previous_km >= 0),
    visit_duration_minutes INTEGER NOT NULL DEFAULT 0 CHECK (visit_duration_minutes >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'visited', 'skipped')),
    UNIQUE (route_plan_id, stop_order)
);

-- 6. Distributor Clusters (Week 12: K-Means Unsupervised Learning)
CREATE TABLE IF NOT EXISTS distributor_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
    cluster_number INTEGER NOT NULL CHECK (cluster_number >= 0),
    cluster_label VARCHAR(100),
    centroid_latitude DOUBLE PRECISION,
    centroid_longitude DOUBLE PRECISION,
    distributor_ids UUID[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (route_plan_id, cluster_number)
);

-- 7. Schedule Entries (Week 5: Constraint Satisfaction Problem)
CREATE TABLE IF NOT EXISTS schedule_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
    distributor_id UUID REFERENCES distributors(id) ON DELETE SET NULL,
    distributor_name VARCHAR(180) NOT NULL,
    scheduled_start TIMESTAMPTZ NOT NULL,
    scheduled_end TIMESTAMPTZ NOT NULL,
    visit_duration_minutes INTEGER NOT NULL CHECK (visit_duration_minutes > 0),
    priority SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    cluster_number INTEGER,
    officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL,
    travel_from_previous_minutes INTEGER,
    distance_from_previous_km DOUBLE PRECISION,
    data_source VARCHAR(40) DEFAULT 'simulated_fallback',
    is_feasible BOOLEAN NOT NULL DEFAULT TRUE,
    constraint_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (scheduled_end > scheduled_start)
);

-- 8. Algorithm Runs (Weeks 3, 4, 7: BFS, UCS, A*, GENETIC_ALGORITHM)
CREATE TABLE IF NOT EXISTS algorithm_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
    algorithm_name VARCHAR(50) NOT NULL
        CHECK (algorithm_name IN ('BFS', 'UCS', 'A*', 'GENETIC_ALGORITHM')),
    optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME',
    data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback',
    traffic_calculated_at TIMESTAMPTZ,
    encoded_polyline TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'completed'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    route_order UUID[] NOT NULL DEFAULT '{}',
    route_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_cost DOUBLE PRECISION,
    total_distance_km DOUBLE PRECISION,
    estimated_duration_minutes INTEGER,
    nodes_expanded INTEGER CHECK (nodes_expanded IS NULL OR nodes_expanded >= 0),
    execution_time_ms DOUBLE PRECISION CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0),
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. API Request Logs
CREATE TABLE IF NOT EXISTS api_request_logs (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(60) NOT NULL,
    endpoint VARCHAR(160) NOT NULL,
    status_code INTEGER,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    duration_ms DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Visit Delay Predictions (Discrete Bayesian Network Inference Records)
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

CREATE INDEX IF NOT EXISTS idx_distributors_active ON distributors(is_active);
CREATE INDEX IF NOT EXISTS idx_distributors_coordinates ON distributors(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_route_plans_date ON route_plans(plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_route_plans_officer ON route_plans(officer_id);
CREATE INDEX IF NOT EXISTS idx_route_stops_plan_order ON route_stops(route_plan_id, stop_order);
CREATE INDEX IF NOT EXISTS idx_schedule_entries_plan_start ON schedule_entries(route_plan_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_algorithm_runs_plan ON algorithm_runs(route_plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_request_logs_created ON api_request_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_plan ON visit_delay_predictions(route_plan_id);
CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_dist ON visit_delay_predictions(distributor_id);
CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_created ON visit_delay_predictions(created_at);

COMMIT;
