from __future__ import annotations

from flask import Blueprint
from app.config import redact_secrets
from app.extensions import db
from app.routes.common import require_database
from app.services import (
    apply_migrations_idempotently,
    check_database_health,
    clear_demo_data,
    get_maps_status,
    load_demo_data,
)
from app.utils.responses import fail, ok

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def get_health():
    health = check_database_health()
    maps_status = get_maps_status()
    if not health["connected"]:
        code = (
            "DATABASE_CONNECTION_FAILED"
            if health["configured"]
            else "DATABASE_NOT_CONFIGURED"
        )
        return (
            {
                "success": False,
                "data": {"app": "ok", "database": health, "googleMaps": maps_status},
                "error": {"code": code, "message": health["message"]},
            },
            503,
        )
    return ok({"app": "ok", "database": health, "googleMaps": maps_status}, health["message"])


@health_bp.post("/db/init")
@require_database
def post_db_init():
    try:
        res = apply_migrations_idempotently()
        health = check_database_health()
        return ok({**res, "database": health}, res["message"])
    except Exception as exc:
        db.session.rollback()
        return fail(
            500,
            "SCHEMA_INIT_FAILED",
            f"Failed to verify or initialize database schema: {redact_secrets(str(exc))}",
        )


@health_bp.post("/demo/load")
@require_database
def post_demo_load():
    try:
        res = load_demo_data()
        status = 200 if res.get("alreadyLoaded") else 201
        return ok(res, res.get("message", "Demo dataset loaded."), status)
    except Exception:
        db.session.rollback()
        return fail(
            500,
            "DEMO_LOAD_FAILED",
            "Failed to load demo dataset. Ensure database schema is initialized.",
        )


@health_bp.post("/demo/clear")
@require_database
def post_demo_clear():
    try:
        res = clear_demo_data()
        return ok(
            res,
            "Removed only demo-tagged records; all user-created data was preserved.",
        )
    except Exception:
        db.session.rollback()
        return fail(500, "DEMO_CLEAR_FAILED", "Failed to clear demo data.")
