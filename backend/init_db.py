import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services import apply_migrations_idempotently, load_demo_data, check_database_health

app = create_app()
with app.app_context():
    print("Applying schema migrations...")
    migrations_ok = apply_migrations_idempotently()
    print("Migrations result:", migrations_ok)
    
    print("Loading demo data...")
    seed_result = load_demo_data()
    print("Seed result:", seed_result)
    
    print("Checking database health...")
    health = check_database_health()
    print("Database health:", health)
