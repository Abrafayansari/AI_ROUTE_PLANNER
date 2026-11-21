from __future__ import annotations

import time
from flask import current_app
from sqlalchemy import text

from app.config import redact_secrets
from app.extensions import db
from app.models import Distributor, FieldOfficer, OfficeLocation, RoutePlan

REQUIRED_TABLES = [
    "field_officers",
    "office_locations",
    "distributors",
    "route_plans",
    "route_stops",
    "distributor_clusters",
    "schedule_entries",
    "algorithm_runs",
    "api_request_logs",
    "visit_delay_predictions",
]

DEMO_OFFICER = {
    "name": "Tariq Mahmood (Demo Field Officer)",
    "email": "demo.officer@fieldops.example",
    "phone": "+92-300-5550100",
    "territory": "Karachi Metro District",
    "work_start_time": "09:00",
    "work_end_time": "17:00",
    "max_daily_visits": 10,
}

DEMO_OFFICE = {
    "name": "Karachi Central Hub (Demo)",
    "address": "Plot 14-C, Shahrah-e-Faisal, PECHS Block 6, Karachi",
    "latitude": 24.8607,
    "longitude": 67.0644,
}

DEMO_DISTRIBUTORS = [
    {
        "name": "Clifton Supermart (Demo)",
        "contact_person": "Zainab Raza",
        "phone": "+92-300-5550101",
        "email": "orders@cliftonmart.example",
        "address": "Block 4, Marine Promenade, Clifton, Karachi",
        "latitude": 24.8138,
        "longitude": 67.0299,
        "priority": 5,
        "visit_duration_minutes": 35,
        "opening_time": "08:00",
        "closing_time": "14:00",
        "notes": "Morning delivery check and quarterly stock review.",
    },
    {
        "name": "Saddar Wholesale Bazaar (Demo)",
        "contact_person": "Bilal Siddiqui",
        "phone": "+92-300-5550102",
        "email": "buyer@saddarwholesale.example",
        "address": "Abdullah Haroon Road, Saddar, Karachi",
        "latitude": 24.8532,
        "longitude": 67.0258,
        "priority": 4,
        "visit_duration_minutes": 30,
        "opening_time": "09:00",
        "closing_time": "17:00",
        "notes": "Verify refrigerated shelf stock and invoice reconciliation.",
    },
    {
        "name": "DHA Phase 6 Traders (Demo)",
        "contact_person": "Ayesha Kamran",
        "phone": "+92-300-5550103",
        "email": "supply@dhatraders.example",
        "address": "Khayaban-e-Ittehad, DHA Phase 6, Karachi",
        "latitude": 24.7937,
        "longitude": 67.0647,
        "priority": 4,
        "visit_duration_minutes": 40,
        "opening_time": "08:30",
        "closing_time": "16:30",
        "notes": "High-volume southern urban outlet.",
    },
    {
        "name": "Korangi Logistics Depot (Demo)",
        "contact_person": "Faisal Qureshi",
        "phone": "+92-300-5550104",
        "email": "receiving@korangidepot.example",
        "address": "Sector 15, Korangi Industrial Area, Karachi",
        "latitude": 24.8351,
        "longitude": 67.1294,
        "priority": 5,
        "visit_duration_minutes": 45,
        "opening_time": "09:00",
        "closing_time": "15:30",
        "notes": "Key account — confirm pallet return and cold-chain manifest.",
    },
    {
        "name": "Gulshan Supply Chain (Demo)",
        "contact_person": "Sana Tariq",
        "phone": "+92-300-5550105",
        "email": "desk@gulshansupply.example",
        "address": "Main University Road, Gulshan-e-Iqbal Block 13, Karachi",
        "latitude": 24.9180,
        "longitude": 67.0971,
        "priority": 3,
        "visit_duration_minutes": 30,
        "opening_time": "10:00",
        "closing_time": "18:00",
        "notes": "Standard replenishment and display check.",
    },
    {
        "name": "PECHS Commercial Provisions (Demo)",
        "contact_person": "Hamza Farooq",
        "phone": "+92-300-5550106",
        "email": "procurement@pechsprov.example",
        "address": "Tariq Road Junction, PECHS Block 2, Karachi",
        "latitude": 24.8719,
        "longitude": 67.0598,
        "priority": 3,
        "visit_duration_minutes": 25,
        "opening_time": "09:30",
        "closing_time": "17:30",
        "notes": "Quick invoice sign-off near central hub.",
    },
    {
        "name": "SITE Industrial Distributors (Demo)",
        "contact_person": "Omar Farooq",
        "phone": "+92-300-5550107",
        "email": "ops@sitedist.example",
        "address": "Manghopir Road, SITE Industrial Estate, Karachi",
        "latitude": 24.9045,
        "longitude": 66.9936,
        "priority": 2,
        "visit_duration_minutes": 30,
        "opening_time": "11:00",
        "closing_time": "19:00",
        "notes": "Opens late morning — schedule after 11:00.",
    },
    {
        "name": "North Nazimabad Grocers (Demo)",
        "contact_person": "Hina Javed",
        "phone": "+92-300-5550108",
        "email": "inventory@nazimabadgrocers.example",
        "address": "Shahrah-e-Sher Shah Suri, Block H, North Nazimabad, Karachi",
        "latitude": 24.9389,
        "longitude": 67.0375,
        "priority": 4,
        "visit_duration_minutes": 35,
        "opening_time": "08:00",
        "closing_time": "16:00",
        "notes": "Northern corridor anchor stop.",
    },
    {
        "name": "Gulistan-e-Johar Market Exchange (Demo)",
        "contact_person": "Kamran Sheikh",
        "phone": "+92-300-5550109",
        "email": "store@joharexchange.example",
        "address": "Jauhar Chowrangi, Block 15, Gulistan-e-Johar, Karachi",
        "latitude": 24.9162,
        "longitude": 67.1319,
        "priority": 2,
        "visit_duration_minutes": 25,
        "opening_time": "10:00",
        "closing_time": "18:00",
        "notes": "Promotional display inspection and eastern hub check.",
    },
]


def is_database_configured() -> bool:
    return bool(current_app.config.get("DATABASE_CONFIGURED"))


def check_database_health() -> dict:
    fallback_active = bool(current_app.config.get("DATABASE_FALLBACK_ACTIVE", False))
    fallback_reason = current_app.config.get("DATABASE_FALLBACK_REASON")

    if not is_database_configured():
        return {
            "configured": False,
            "connected": False,
            "dialect": None,
            "activeDatabase": "None",
            "neonReachable": False,
            "neonTablesVerified": False,
            "fallbackActive": False,
            "fallbackReason": None,
            "schemaReady": False,
            "missingTables": list(REQUIRED_TABLES),
            "existingTables": [],
            "latencyMs": None,
            "message": "DATABASE_URL is not configured in server-side Secrets.",
        }

    start_t = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        dialect_name = db.engine.dialect.name
        if dialect_name == "sqlite":
            rows = db.session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            ).fetchall()
            engine_label = "SQLite (local fallback)" if fallback_active else "SQLite database"
        else:
            rows = db.session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                    """
                )
            ).fetchall()
            engine_label = "PostgreSQL"

        latency_ms = round((time.perf_counter() - start_t) * 1000.0)
        present = {str(r[0]) for r in rows}
        existing = [t for t in REQUIRED_TABLES if t in present]
        missing = [t for t in REQUIRED_TABLES if t not in present]
        schema_ready = len(missing) == 0
        is_pg = dialect_name == "postgresql"

        base_msg = (
            f"Connected to {engine_label} ({latency_ms} ms); all {len(REQUIRED_TABLES)} schema tables verified."
            if schema_ready
            else f"Connected to {engine_label} ({latency_ms} ms), but {len(missing)} required table(s) are missing: {', '.join(missing)}."
        )
        message = (
            f"SQLite fallback active ({fallback_reason}). {base_msg}"
            if fallback_active and fallback_reason
            else base_msg
        )

        return {
            "configured": True,
            "connected": True,
            "dialect": dialect_name,
            "activeDatabase": engine_label,
            "neonReachable": is_pg,
            "neonTablesVerified": is_pg and schema_ready,
            "fallbackActive": fallback_active,
            "fallbackReason": fallback_reason,
            "schemaReady": schema_ready,
            "missingTables": missing,
            "existingTables": existing,
            "latencyMs": latency_ms,
            "message": message,
        }
    except Exception as exc:
        return {
            "configured": True,
            "connected": False,
            "dialect": None,
            "activeDatabase": "None",
            "neonReachable": False,
            "neonTablesVerified": False,
            "fallbackActive": fallback_active,
            "fallbackReason": fallback_reason,
            "schemaReady": False,
            "missingTables": list(REQUIRED_TABLES),
            "existingTables": [],
            "latencyMs": None,
            "message": f"Database connection failed: {redact_secrets(str(exc))}",
        }


def apply_migrations_idempotently() -> dict:
    """
    Idempotently create missing tables/columns without ever dropping tables or
    deleting existing records in Neon PostgreSQL or SQLite test databases.
    """
    applied: list[str] = []

    if db.engine.dialect.name == "sqlite":
        db.create_all()
        applied.append("sqlite_create_all_verified")
        return {
            "applied": applied,
            "message": "SQLite database schema verified without altering existing data.",
        }

    ddl_statements = [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
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
        """,
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
        """,
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
        """,
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
            distance_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            graph_seed INTEGER NOT NULL DEFAULT 42,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            map_provider VARCHAR(40) NOT NULL DEFAULT 'simulated',
            notes TEXT DEFAULT '',
            is_demo BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS route_stops (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
            distributor_id UUID REFERENCES distributors(id) ON DELETE SET NULL,
            stop_order INTEGER NOT NULL,
            stop_name VARCHAR(180) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            estimated_arrival TIMESTAMPTZ,
            estimated_departure TIMESTAMPTZ,
            travel_from_previous_minutes INTEGER,
            distance_from_previous_km DOUBLE PRECISION,
            visit_duration_minutes INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            UNIQUE (route_plan_id, stop_order)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS distributor_clusters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
            cluster_number INTEGER NOT NULL,
            cluster_label VARCHAR(100),
            centroid_latitude DOUBLE PRECISION,
            centroid_longitude DOUBLE PRECISION,
            distributor_ids UUID[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (route_plan_id, cluster_number)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS schedule_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
            distributor_id UUID REFERENCES distributors(id) ON DELETE SET NULL,
            distributor_name VARCHAR(180) NOT NULL,
            scheduled_start TIMESTAMPTZ NOT NULL,
            scheduled_end TIMESTAMPTZ NOT NULL,
            visit_duration_minutes INTEGER NOT NULL,
            priority SMALLINT NOT NULL DEFAULT 3,
            cluster_number INTEGER,
            is_feasible BOOLEAN NOT NULL DEFAULT TRUE,
            constraint_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS algorithm_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID NOT NULL REFERENCES route_plans(id) ON DELETE CASCADE,
            algorithm_name VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'completed',
            route_order UUID[] NOT NULL DEFAULT '{}',
            route_names JSONB NOT NULL DEFAULT '[]'::jsonb,
            total_cost DOUBLE PRECISION,
            total_distance_km DOUBLE PRECISION,
            estimated_duration_minutes INTEGER,
            nodes_expanded INTEGER,
            execution_time_ms DOUBLE PRECISION,
            parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_details JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        """
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
        """,
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_plan ON visit_delay_predictions(route_plan_id);",
        "CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_dist ON visit_delay_predictions(distributor_id);",
        "CREATE INDEX IF NOT EXISTS idx_visit_delay_predictions_created ON visit_delay_predictions(created_at);",
        "ALTER TABLE field_officers ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE office_locations ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE distributors ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS map_provider VARCHAR(40) NOT NULL DEFAULT 'simulated';",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS stop_name VARCHAR(180) NOT NULL DEFAULT '';",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION NOT NULL DEFAULT 0;",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION NOT NULL DEFAULT 0;",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS travel_from_previous_minutes INTEGER;",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS distance_from_previous_km DOUBLE PRECISION;",
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS visit_duration_minutes INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS route_plan_id UUID REFERENCES route_plans(id) ON DELETE CASCADE;",
        "ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS cluster_number INTEGER;",
        "ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS centroid_latitude DOUBLE PRECISION;",
        "ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS centroid_longitude DOUBLE PRECISION;",
        "ALTER TABLE distributor_clusters ADD COLUMN IF NOT EXISTS distributor_ids UUID[] NOT NULL DEFAULT '{}';",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS distributor_name VARCHAR(180) NOT NULL DEFAULT '';",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS scheduled_start TIMESTAMPTZ;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS scheduled_end TIMESTAMPTZ;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS visit_duration_minutes INTEGER NOT NULL DEFAULT 30;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 3;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS cluster_number INTEGER;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed';",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS route_order UUID[] NOT NULL DEFAULT '{}';",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS route_names JSONB NOT NULL DEFAULT '[]'::jsonb;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS total_distance_km DOUBLE PRECISION;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS parameters JSONB NOT NULL DEFAULT '{}'::jsonb;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS result_details JSONB NOT NULL DEFAULT '{}'::jsonb;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS error_message TEXT;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS normal_duration_minutes INTEGER;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS traffic_delay_minutes INTEGER;",
        "ALTER TABLE route_plans ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;",
        "ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_travel_mode_check;",
        """
        ALTER TABLE route_plans ADD CONSTRAINT route_plans_travel_mode_check
          CHECK (travel_mode IN ('simulated_vehicle', 'simulated_walking', 'simulated_van', 'DRIVE', 'TWO_WHEELER', 'WALK'));
        """,
        "ALTER TABLE route_plans DROP CONSTRAINT IF EXISTS route_plans_optimization_objective_check;",
        """
        ALTER TABLE route_plans ADD CONSTRAINT route_plans_optimization_objective_check
          CHECK (optimization_objective IN ('FASTEST_TIME', 'SHORTEST_DISTANCE'));
        """,
        "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS static_travel_from_previous_minutes INTEGER;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS optimization_objective VARCHAR(30) NOT NULL DEFAULT 'FASTEST_TIME';",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) NOT NULL DEFAULT 'simulated_fallback';",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS traffic_calculated_at TIMESTAMPTZ;",
        "ALTER TABLE algorithm_runs ADD COLUMN IF NOT EXISTS encoded_polyline TEXT;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS officer_id UUID REFERENCES field_officers(id) ON DELETE SET NULL;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS travel_from_previous_minutes INTEGER;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS distance_from_previous_km DOUBLE PRECISION;",
        "ALTER TABLE schedule_entries ADD COLUMN IF NOT EXISTS data_source VARCHAR(40) DEFAULT 'simulated_fallback';",
    ]

    for stmt in ddl_statements:
        db.session.execute(text(stmt))
    db.session.commit()
    applied.append("001_004_idempotent_schema_verified")

    return {
        "applied": applied,
        "message": "Neon PostgreSQL schema verified and aligned without altering existing data.",
    }



def load_demo_data() -> dict:
    apply_migrations_idempotently()
    existing_demo = db.session.query(Distributor).filter_by(is_demo=True).count()
    if existing_demo > 0:
        return {
            "alreadyLoaded": True,
            "message": "Demo dataset is already present. No existing data was overwritten.",
        }

    officer = db.session.query(FieldOfficer).filter_by(email=DEMO_OFFICER["email"]).first()
    if officer is None:
        officer = FieldOfficer(
            name=DEMO_OFFICER["name"],
            email=DEMO_OFFICER["email"],
            phone=DEMO_OFFICER["phone"],
            territory=DEMO_OFFICER["territory"],
            work_start_time=DEMO_OFFICER["work_start_time"],
            work_end_time=DEMO_OFFICER["work_end_time"],
            max_daily_visits=DEMO_OFFICER["max_daily_visits"],
            is_demo=True,
        )
        db.session.add(officer)
        db.session.flush()
    else:
        officer.name = DEMO_OFFICER["name"]
        officer.is_demo = True

    first_office = db.session.query(OfficeLocation).first()
    if first_office is None:
        office = OfficeLocation(
            name=DEMO_OFFICE["name"],
            address=DEMO_OFFICE["address"],
            latitude=DEMO_OFFICE["latitude"],
            longitude=DEMO_OFFICE["longitude"],
            is_default=True,
            is_demo=True,
        )
        db.session.add(office)
        db.session.flush()
        office_id = str(office.id)
    else:
        office_id = str(first_office.id)

    added = 0
    for d in DEMO_DISTRIBUTORS:
        db.session.add(
            Distributor(
                name=d["name"],
                contact_person=d["contact_person"],
                phone=d["phone"],
                email=d["email"],
                address=d["address"],
                latitude=d["latitude"],
                longitude=d["longitude"],
                priority=d["priority"],
                visit_duration_minutes=d["visit_duration_minutes"],
                opening_time=d["opening_time"],
                closing_time=d["closing_time"],
                is_active=True,
                notes=d["notes"],
                is_demo=True,
            )
        )
        added += 1

    db.session.commit()
    return {
        "officerId": str(officer.id),
        "officeId": office_id,
        "addedDistributors": added,
        "message": f"Loaded {added} demo distributors without modifying any user records.",
    }


def clear_demo_data() -> dict:
    rp_count = db.session.query(RoutePlan).filter_by(is_demo=True).delete()
    dist_count = db.session.query(Distributor).filter_by(is_demo=True).delete()
    off_count = db.session.query(OfficeLocation).filter_by(is_demo=True).delete()
    fo_count = db.session.query(FieldOfficer).filter_by(is_demo=True).delete()
    db.session.commit()
    return {
        "routePlansRemoved": int(rp_count or 0),
        "distributorsRemoved": int(dist_count or 0),
        "officesRemoved": int(off_count or 0),
        "officersRemoved": int(fo_count or 0),
    }


def log_api_request(
    provider: str, endpoint: str, status_code: int, success: bool, duration_ms: float
) -> None:
    from flask import has_app_context

    if not has_app_context() or not is_database_configured():
        return
    try:
        db.session.execute(
            text(
                """
                INSERT INTO api_request_logs (provider, endpoint, status_code, success, duration_ms)
                VALUES (:provider, :endpoint, :status_code, :success, :duration_ms)
                """
            ),
            {
                "provider": provider[:60],
                "endpoint": endpoint[:160],
                "status_code": int(status_code),
                "success": bool(success),
                "duration_ms": float(duration_ms),
            },
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
