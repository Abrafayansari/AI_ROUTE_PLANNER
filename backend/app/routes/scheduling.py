from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from app.config import redact_secrets
from app.extensions import db
from app.routes.common import pydantic_error_response, rate_limit, require_database
from app.services import get_latest_schedule, run_and_save_schedule
from app.utils.responses import fail, ok
from app.utils.validation import ScheduleRunInput

scheduling_bp = Blueprint("scheduling", __name__)


@scheduling_bp.get("/schedules/latest")
@require_database
def latest_schedule():
    try:
        data = get_latest_schedule()
        if data is None:
            return ok(None, "No schedules generated yet.")
        return ok(data)
    except Exception as exc:
        print("GET /api/schedules/latest error:", redact_secrets(str(exc)))
        return fail(500, "DB_ERROR", "Failed to load latest schedule.")


@scheduling_bp.post("/schedules/run")
@require_database
@rate_limit(30, 60.0)
def run_schedule():
    try:
        parsed = ScheduleRunInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        result = run_and_save_schedule(parsed.model_dump())
        return ok(result, "CSP visit schedule generated and persisted.")
    except LookupError as exc:
        db.session.rollback()
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except ValueError as exc:
        db.session.rollback()
        if str(exc) == "NO_OFFICE_LOCATION":
            return fail(
                400,
                "NO_OFFICE_LOCATION",
                "Create an office location first so schedules can attach to a route plan.",
            )
        return fail(400, "CSP_ERROR", str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail(400, "CSP_ERROR", str(exc))
