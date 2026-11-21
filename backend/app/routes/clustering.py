from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from app.extensions import db
from app.routes.common import pydantic_error_response, rate_limit, require_database
from app.services import get_latest_clusters, run_and_save_clusters
from app.utils.responses import fail, ok
from app.utils.validation import ClusterRunInput

clustering_bp = Blueprint("clustering", __name__)


@clustering_bp.get("/clusters/latest")
@require_database
def latest_clusters():
    try:
        data = get_latest_clusters()
        if data is None:
            return ok(None, "No clustering runs recorded yet.")
        return ok(data)
    except Exception:
        return fail(500, "DB_ERROR", "Failed to load latest clusters.")


@clustering_bp.post("/clusters/run")
@require_database
@rate_limit(30, 60.0)
def run_clusters():
    try:
        parsed = ClusterRunInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        result = run_and_save_clusters(parsed.model_dump())
        return ok(result, "K-Means clustering completed and saved.")
    except LookupError as exc:
        db.session.rollback()
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except ValueError as exc:
        db.session.rollback()
        if str(exc) == "NO_OFFICE_LOCATION":
            return fail(
                400,
                "NO_OFFICE_LOCATION",
                "Create an office location first so clustering can attach to a route plan.",
            )
        return fail(400, "VALIDATION_ERROR", str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail(400, "CLUSTERING_ERROR", str(exc))
