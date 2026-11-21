from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from app.routes.common import pydantic_error_response, rate_limit
from app.services.routing_service import (
    AllRoutingProvidersFailedError,
    compute_route_geometry_with_routing,
    get_routing_status,
)
from app.utils.responses import fail, ok
from app.utils.validation import RouteGeometryInput

maps_bp = Blueprint("maps", __name__)


@maps_bp.get("/maps/status")
def maps_status():
    return ok(get_routing_status())


@maps_bp.post("/maps/route-geometry")
@rate_limit(30, 60.0)
def post_route_geometry():
    try:
        parsed = RouteGeometryInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    waypoints = [
        {"latitude": wp.latitude, "longitude": wp.longitude}
        for wp in parsed.waypoints
    ]
    try:
        data = compute_route_geometry_with_routing(
            waypoints,
            travel_mode=parsed.travelMode,
            optimization_objective=parsed.optimizationObjective,
        )
        return ok(data)
    except AllRoutingProvidersFailedError as exc:
        return fail(503, "ROUTING_PROVIDERS_UNAVAILABLE", str(exc), details=exc.to_details())
    except ValueError as exc:
        return fail(400, "VALIDATION_ERROR", str(exc))
