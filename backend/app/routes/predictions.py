from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from app.config import redact_secrets
from app.extensions import db
from app.routes.common import pydantic_error_response, require_database
from app.services.prediction_service import (
    get_cpt_data,
    get_model_info,
    list_prediction_history,
    predict_route_plan_delays,
    predict_single_visit,
)
from app.utils.responses import fail, ok
from app.utils.validation import RouteDelayInput, VisitDelayInput

predictions_bp = Blueprint("predictions", __name__)


@predictions_bp.get("/predictions/model-info")
def get_model_information():
    """Return Bayesian Network structure, variables, CPT configuration, and validation status."""
    try:
        data = get_model_info()
        return ok(data)
    except Exception as exc:
        return fail(500, "MODEL_INFO_ERROR", f"Failed to retrieve model info: {redact_secrets(str(exc))}")


@predictions_bp.get("/predictions/cpt")
def get_cpt_table():
    """Return the 54-row Conditional Probability Table for visualization."""
    try:
        data = get_cpt_data()
        return ok(data)
    except Exception as exc:
        return fail(500, "CPT_ERROR", f"Failed to retrieve CPT table: {redact_secrets(str(exc))}")


@predictions_bp.post("/predictions/visit-delay")
def post_visit_delay():
    """
    Calculate delay probabilities for a single distributor visit using
    supplied evidence or saved distributor information.
    """
    try:
        parsed = VisitDelayInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = predict_single_visit(parsed.model_dump())
        return ok(data, f"Visit delay risk evaluated: {data['predictedRisk']}.")
    except ValueError as exc:
        return fail(400, "INVALID_EVIDENCE", str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail(500, "PREDICTION_ERROR", f"Failed to calculate visit delay risk: {redact_secrets(str(exc))}")


@predictions_bp.post("/predictions/route-delay")
@require_database
def post_route_delay():
    """
    Calculate delay probabilities for all stops in a saved route plan in Neon PostgreSQL.
    """
    try:
        parsed = RouteDelayInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = predict_route_plan_delays(parsed.routePlanId, save_to_db=parsed.saveToDb)
        return ok(
            data,
            f"Evaluated delay risks for {data['totalEvaluated']} stops in route plan.",
        )
    except FileNotFoundError as exc:
        return fail(404, "NOT_FOUND", str(exc))
    except ValueError as exc:
        return fail(400, "INVALID_ROUTE_PLAN", str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail(500, "ROUTE_PREDICTION_ERROR", f"Failed to predict route delays: {redact_secrets(str(exc))}")


@predictions_bp.get("/predictions/visit-delay/history")
@require_database
def get_prediction_history():
    """Retrieve saved visit delay predictions from Neon PostgreSQL."""
    try:
        plan_id = request.args.get("routePlanId")
        limit = int(request.args.get("limit") or 50)
        items = list_prediction_history(route_plan_id=plan_id, limit=limit)
        return ok({"items": items, "count": len(items)})
    except Exception as exc:
        return fail(500, "DB_ERROR", f"Failed to load prediction history: {redact_secrets(str(exc))}")
