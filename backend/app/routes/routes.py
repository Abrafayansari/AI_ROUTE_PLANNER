from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from app.config import redact_secrets
from app.extensions import db
from app.routes.common import pydantic_error_response, rate_limit, require_database
from app.services import (
    create_route_plan,
    delete_route_plan,
    generate_local_matrix,
    get_analytics_summary,
    get_route_plan_algorithms,
    get_route_plan_detail,
    list_route_plans,
    optimize_route_plan,
    preview_optimization,
    update_route_plan,
    update_stop_status,
)
from app.utils.responses import fail, ok
from app.utils.validation import (
    CreateRoutePlanInput,
    GraphMatrixInput,
    OptimizePreviewInput,
    OptimizeRouteInput,
    StopStatusInput,
    UpdateRoutePlanInput,
    is_valid_uuid,
)

routes_bp = Blueprint("routes", __name__)


@routes_bp.post("/graph/matrix")
@require_database
def post_graph_matrix():
    try:
        parsed = GraphMatrixInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = generate_local_matrix(parsed.model_dump())
        return ok(data)
    except FileNotFoundError as exc:
        return fail(404, "NOT_FOUND", str(exc))
    except LookupError as exc:
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except Exception:
        return fail(500, "MATRIX_ERROR", "Failed to generate local cost matrix.")


@routes_bp.post("/optimize/preview")
@require_database
@rate_limit(30, 60.0)
def post_optimize_preview():
    try:
        parsed = OptimizePreviewInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = preview_optimization(parsed.model_dump())
        return ok(data)
    except FileNotFoundError as exc:
        return fail(404, "NOT_FOUND", str(exc))
    except LookupError as exc:
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except Exception as exc:
        print("POST /api/optimize/preview error:", redact_secrets(str(exc)))
        return fail(
            500, "OPTIMIZATION_ERROR", "Failed to run search algorithm comparison."
        )


@routes_bp.get("/route-plans")
@require_database
def get_route_plans():
    try:
        page = max(1, int(request.args.get("page") or 1))
        page_size = min(50, max(1, int(request.args.get("pageSize") or 20)))
        data = list_route_plans(page=page, page_size=page_size)
        return ok(data)
    except Exception:
        return fail(500, "DB_ERROR", "Failed to load route plans.")


@routes_bp.post("/route-plans")
@require_database
def post_route_plan():
    try:
        parsed = CreateRoutePlanInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = create_route_plan(parsed.model_dump())
        return ok(data, "Route plan created in Neon PostgreSQL.", 201)
    except FileNotFoundError as exc:
        db.session.rollback()
        return fail(404, "NOT_FOUND", str(exc))
    except LookupError as exc:
        db.session.rollback()
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to create route plan.")


@routes_bp.post("/route-plans/<plan_id>/optimize")
@require_database
@rate_limit(30, 60.0)
def post_optimize_route_plan(plan_id: str):
    if not is_valid_uuid(plan_id):
        return fail(400, "INVALID_ID", "Invalid route plan ID format.")

    try:
        parsed = OptimizeRouteInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = optimize_route_plan(plan_id, parsed.model_dump())
        return ok(
            data,
            f"Optimized route plan using {data['selectedAlgorithm']} (recommended: {data['recommendedAlgorithm']}).",
        )
    except FileNotFoundError as exc:
        db.session.rollback()
        return fail(404, "NOT_FOUND", str(exc))
    except LookupError as exc:
        db.session.rollback()
        return fail(400, "INVALID_DISTRIBUTORS", str(exc))
    except ValueError as exc:
        db.session.rollback()
        return fail(400, "NO_DISTRIBUTORS", str(exc))
    except Exception as exc:
        db.session.rollback()
        print("POST /api/route-plans/<id>/optimize error:", redact_secrets(str(exc)))
        return fail(500, "OPTIMIZATION_ERROR", "Failed to optimize route plan.")


@routes_bp.get("/route-plans/<plan_id>")
@require_database
def get_route_plan(plan_id: str):
    if not is_valid_uuid(plan_id):
        return fail(400, "INVALID_ID", "Invalid route plan ID format.")
    try:
        data = get_route_plan_detail(plan_id)
        return ok(data)
    except FileNotFoundError as exc:
        return fail(404, "NOT_FOUND", str(exc))
    except Exception:
        return fail(500, "DB_ERROR", "Failed to fetch route plan details.")


@routes_bp.get("/route-plans/<plan_id>/algorithms")
@require_database
def get_algorithms_for_plan(plan_id: str):
    if not is_valid_uuid(plan_id):
        return fail(400, "INVALID_ID", "Invalid route plan ID format.")
    try:
        return ok(get_route_plan_algorithms(plan_id))
    except Exception:
        return fail(500, "DB_ERROR", "Failed to load algorithm comparison results.")


@routes_bp.put("/route-plans/<plan_id>")
@require_database
def put_route_plan(plan_id: str):
    if not is_valid_uuid(plan_id):
        return fail(400, "INVALID_ID", "Invalid route plan ID format.")

    try:
        parsed = UpdateRoutePlanInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        data = update_route_plan(plan_id, parsed.model_dump())
        return ok(data, "Route plan updated")
    except FileNotFoundError:
        db.session.rollback()
        return fail(404, "NOT_FOUND", "Route plan not found.")
    except Exception as exc:
        db.session.rollback()
        print("PUT /api/route-plans/<id> error:", redact_secrets(str(exc)))
        return fail(500, "DB_ERROR", "Failed to update route plan.")


@routes_bp.delete("/route-plans/<plan_id>")
@require_database
def delete_plan(plan_id: str):
    if not is_valid_uuid(plan_id):
        return fail(400, "INVALID_ID", "Invalid route plan ID format.")
    try:
        deleted = delete_route_plan(plan_id)
        if not deleted:
            return fail(404, "NOT_FOUND", "Route plan not found.")
        return ok({"id": plan_id}, "Route plan deleted")
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to delete route plan.")


@routes_bp.patch("/route-stops/<stop_id>/status")
@require_database
def patch_stop_status(stop_id: str):
    if not is_valid_uuid(stop_id):
        return fail(400, "INVALID_ID", "Invalid stop ID format.")

    try:
        parsed = StopStatusInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        result = update_stop_status(stop_id, parsed.status)
        if result is None:
            return fail(404, "NOT_FOUND", "Route stop not found.")
        return ok(result, "Route stop status updated.")
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to update route stop status.")


@routes_bp.get("/analytics/summary")
@require_database
def analytics_summary():
    try:
        data = get_analytics_summary()
        return ok(data)
    except Exception as exc:
        print("GET /api/analytics/summary error:", redact_secrets(str(exc)))
        return fail(500, "DB_ERROR", "Failed to compute analytics summary.")
