from __future__ import annotations

import time
from flask import Flask, g, request

from app.config import Config, redact_secrets
from app.extensions import cors, db, migrate
from app.routes import (
    clustering_bp,
    distributors_bp,
    health_bp,
    office_bp,
    predictions_bp,
    routes_bp,
    scheduling_bp,
)
from app.services import apply_migrations_idempotently, log_api_request
from app.utils.responses import fail


def create_app(config_overrides: dict | None = None) -> Flask:
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    if config_overrides:
        flask_app.config.update(config_overrides)

    db.init_app(flask_app)
    migrate.init_app(flask_app, db, directory="migrations")
    cors.init_app(
        flask_app,
        resources={r"/api/*": {"origins": flask_app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True,
    )

    # Import models so Flask-Migrate / SQLAlchemy metadata sees all tables
    import app.models  # noqa: F401

    flask_app.register_blueprint(health_bp, url_prefix="/api")
    flask_app.register_blueprint(office_bp, url_prefix="/api")
    flask_app.register_blueprint(distributors_bp, url_prefix="/api")
    flask_app.register_blueprint(clustering_bp, url_prefix="/api")
    flask_app.register_blueprint(scheduling_bp, url_prefix="/api")
    flask_app.register_blueprint(routes_bp, url_prefix="/api")
    flask_app.register_blueprint(predictions_bp, url_prefix="/api")

    @flask_app.before_request
    def _track_start():
        g.req_start_t = time.perf_counter()

    @flask_app.after_request
    def _log_request(response):
        if (
            flask_app.config.get("DATABASE_CONFIGURED")
            and not flask_app.config.get("TESTING")
            and request.path.startswith("/api/")
            and request.path != "/api/health"
        ):
            start_t = getattr(g, "req_start_t", None)
            duration_ms = (
                round((time.perf_counter() - start_t) * 1000.0, 2)
                if start_t is not None
                else 0.0
            )
            provider = (
                "local_simulated_graph"
                if ("/optimize" in request.path or "/graph" in request.path)
                else "internal_api"
            )
            log_api_request(
                provider=provider,
                endpoint=f"{request.method} {request.path}",
                status_code=response.status_code,
                success=response.status_code < 400,
                duration_ms=duration_ms,
            )
        return response

    @flask_app.errorhandler(404)
    def _not_found(_err):
        if request.path.startswith("/api/"):
            return fail(404, "API_NOT_FOUND", "Requested API endpoint does not exist.")
        return fail(404, "NOT_FOUND", "Resource not found.")

    if flask_app.config.get("DATABASE_CONFIGURED") and not flask_app.config.get("TESTING"):
        with flask_app.app_context():
            try:
                res = apply_migrations_idempotently()
                print(f"Neon schema verified: {', '.join(res['applied'])}")
            except Exception as exc:
                print(f"Neon startup schema check skipped: {redact_secrets(str(exc))}")

    return flask_app
