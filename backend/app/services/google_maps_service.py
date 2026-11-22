from __future__ import annotations

from collections import OrderedDict, deque
from datetime import datetime, timezone
import os
import threading
import time
from typing import Any

from flask import current_app, has_app_context
import requests

from app.config import redact_secrets
from app.services.db_service import log_api_request
from app.utils.metrics import (
    CostMatrixResult,
    OptimizationObjective,
    TravelMode,
    build_local_cost_matrix,
    get_simulated_speed_kmh,
)

OBJECTIVE_FASTEST_TIME: OptimizationObjective = "FASTEST_TIME"
OBJECTIVE_SHORTEST_DISTANCE: OptimizationObjective = "SHORTEST_DISTANCE"

DATA_SOURCE_GOOGLE_LIVE_TRAFFIC = "google_live_traffic"
DATA_SOURCE_GOOGLE_ROAD_DISTANCE = "google_road_distance"

COMPUTE_ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
COMPUTE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ATTRIBUTION_SOLUTION_ID = "gmp_mcp_codeassist_v1_aistudio"

MATRIX_CHUNK_SIZE = 10  # 10 x 10 = 100 elements max per computeRouteMatrix call
MAX_CACHE_ENTRIES = 100
TTL_FASTEST_TIME_SEC = 300.0
TTL_SHORTEST_DISTANCE_SEC = 1800.0
GOOGLE_MAX_RPM = 60

_CACHE_LOCK = threading.Lock()
_GOOGLE_MATRIX_CACHE: OrderedDict[str, tuple[float, CostMatrixResult]] = OrderedDict()
_GOOGLE_GEOMETRY_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_RATE_TIMESTAMPS: deque[float] = deque()


def clear_google_maps_caches() -> None:
    with _CACHE_LOCK:
        _GOOGLE_MATRIX_CACHE.clear()
        _GOOGLE_GEOMETRY_CACHE.clear()
        _RATE_TIMESTAMPS.clear()


def get_google_server_api_key() -> str | None:
    from app.config import is_placeholder_api_key

    key = None
    if has_app_context():
        key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not key:
        key = os.getenv("GOOGLE_MAPS_API_KEY")
    key_str = str(key or "").strip()
    if not key_str or is_placeholder_api_key(key_str):
        return None
    return key_str


def resolve_google_travel_mode(mode: str | None) -> str:
    if mode in ("simulated_walking", "WALK"):
        return "WALK"
    if mode == "TWO_WHEELER":
        return "TWO_WHEELER"
    return "DRIVE"


def _check_rate_limit() -> bool:
    now = time.monotonic()
    with _CACHE_LOCK:
        while _RATE_TIMESTAMPS and (now - _RATE_TIMESTAMPS[0]) > 60.0:
            _RATE_TIMESTAMPS.popleft()
        if len(_RATE_TIMESTAMPS) >= GOOGLE_MAX_RPM:
            return False
        _RATE_TIMESTAMPS.append(now)
        return True


def _parse_duration_minutes(raw_duration: str | None) -> float | None:
    if not raw_duration or not isinstance(raw_duration, str):
        return None
    cleaned = raw_duration.strip()
    if cleaned.endswith("s"):
        cleaned = cleaned[:-1]
    try:
        seconds = float(cleaned)
        return round(max(0.0, seconds / 60.0), 2)
    except ValueError:
        return None


def _matrix_data_source(google_mode: str, objective: OptimizationObjective) -> str:
    if objective == OBJECTIVE_FASTEST_TIME and google_mode in ("DRIVE", "TWO_WHEELER"):
        return DATA_SOURCE_GOOGLE_LIVE_TRAFFIC
    return DATA_SOURCE_GOOGLE_ROAD_DISTANCE


def _waypoint_payload(node: dict) -> dict:
    return {
        "waypoint": {
            "location": {
                "latLng": {
                    "latitude": float(node["latitude"]),
                    "longitude": float(node["longitude"]),
                }
            }
        }
    }


def fetch_google_cost_matrix(
    nodes: list[dict],
    seed: int = 42,
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> CostMatrixResult:
    """
    Fetch directed N x N road distance & duration matrix from Google Routes API (computeRouteMatrix).
    Raises RuntimeError if unconfigured, rate-limited, or upstream call fails.
    Never falls back silently to simulated Haversine data.
    """
    api_key = get_google_server_api_key()
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured.")

    n = len(nodes)
    google_mode = resolve_google_travel_mode(travel_mode)
    coord_sig = "|".join(
        f"{nd['id']}:{float(nd['latitude']):.6f},{float(nd['longitude']):.6f}" for nd in nodes
    )
    cache_key = f"google|{google_mode}|{optimization_objective}|{coord_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _GOOGLE_MATRIX_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_res = cached
            if now < expires_at:
                _GOOGLE_MATRIX_CACHE.move_to_end(cache_key)
                return CostMatrixResult(
                    nodes=cached_res.nodes,
                    straightLineKm=cached_res.straightLineKm,
                    distanceKm=cached_res.distanceKm,
                    durationMinutes=cached_res.durationMinutes,
                    staticDurationMinutes=cached_res.staticDurationMinutes,
                    seed=cached_res.seed,
                    distanceMultiplier=cached_res.distanceMultiplier,
                    travelMode=travel_mode,
                    speedKmh=cached_res.speedKmh,
                    cacheHit=True,
                    matrixKey=cached_res.matrixKey,
                    optimizationObjective=optimization_objective,
                    provider=cached_res.provider,
                    providerLabel=cached_res.providerLabel,
                    dataSource=cached_res.dataSource,
                    isLiveTraffic=cached_res.isLiveTraffic,
                    durationType=cached_res.durationType,
                    durationLabel=cached_res.durationLabel,
                    trafficCalculatedAt=cached_res.trafficCalculatedAt,
                    calculatedAt=cached_res.calculatedAt,
                    fallbackReason=None,
                    providerAttempts=list(cached_res.providerAttempts),
                    roadDistanceAvailable=cached_res.roadDistanceAvailable,
                )
            _GOOGLE_MATRIX_CACHE.pop(cache_key, None)

    if not _check_rate_limit():
        raise RuntimeError("Google Routes API rate limit guard reached.")

    straight_line = build_local_cost_matrix(
        nodes,
        seed=seed,
        distance_multiplier=1.0,
        travel_mode=travel_mode,
        optimization_objective=optimization_objective,
    ).straightLineKm

    distance_km = [[0.0 for _ in range(n)] for _ in range(n)]
    duration_min = [[0.0 for _ in range(n)] for _ in range(n)]
    static_duration_min = [[0.0 for _ in range(n)] for _ in range(n)]
    seen_pairs: set[tuple[int, int]] = set()

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-Maps-Solution-ID": ATTRIBUTION_SOLUTION_ID,
        "X-Goog-FieldMask": (
            "originIndex,destinationIndex,duration,staticDuration,distanceMeters,status,condition"
        ),
    }

    try:
        for o_start in range(0, n, MATRIX_CHUNK_SIZE):
            o_end = min(n, o_start + MATRIX_CHUNK_SIZE)
            origins_chunk = [_waypoint_payload(nodes[i]) for i in range(o_start, o_end)]

            for d_start in range(0, n, MATRIX_CHUNK_SIZE):
                d_end = min(n, d_start + MATRIX_CHUNK_SIZE)
                destinations_chunk = [_waypoint_payload(nodes[j]) for j in range(d_start, d_end)]

                body: dict[str, Any] = {
                    "origins": origins_chunk,
                    "destinations": destinations_chunk,
                    "travelMode": google_mode,
                }
                if google_mode in ("DRIVE", "TWO_WHEELER"):
                    body["routingPreference"] = (
                        "TRAFFIC_AWARE"
                        if optimization_objective == OBJECTIVE_FASTEST_TIME
                        else "TRAFFIC_UNAWARE"
                    )

                t0 = time.perf_counter()
                resp = requests.post(
                    COMPUTE_ROUTE_MATRIX_URL,
                    json=body,
                    headers=headers,
                    timeout=15.0,
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                log_api_request(
                    provider="google_routes",
                    endpoint="computeRouteMatrix",
                    status_code=resp.status_code,
                    success=resp.status_code == 200,
                    duration_ms=elapsed_ms,
                )

                if resp.status_code != 200:
                    raise RuntimeError(f"Google Routes computeRouteMatrix HTTP {resp.status_code}")

                elements = resp.json()
                if not isinstance(elements, list):
                    raise RuntimeError("Invalid computeRouteMatrix JSON payload")

                for elem in elements:
                    oi = elem.get("originIndex")
                    di = elem.get("destinationIndex")
                    if oi is None or di is None:
                        continue
                    gi = o_start + int(oi)
                    gj = d_start + int(di)
                    if gi == gj:
                        distance_km[gi][gj] = 0.0
                        duration_min[gi][gj] = 0.0
                        static_duration_min[gi][gj] = 0.0
                        seen_pairs.add((gi, gj))
                        continue

                    condition = elem.get("condition")
                    if condition and condition != "ROUTE_EXISTS":
                        raise RuntimeError(f"Google route condition {condition} for ({gi}->{gj})")

                    status_obj = elem.get("status")
                    if isinstance(status_obj, dict) and status_obj.get("code", 0) not in (0, None):
                        raise RuntimeError(f"Google route element error for ({gi}->{gj})")

                    meters = elem.get("distanceMeters")
                    dur_m = _parse_duration_minutes(elem.get("duration"))
                    static_m = _parse_duration_minutes(elem.get("staticDuration")) or dur_m
                    if meters is None or dur_m is None:
                        raise RuntimeError(f"Missing distanceMeters or duration for ({gi}->{gj})")

                    distance_km[gi][gj] = round(float(meters) / 1000.0, 3)
                    duration_min[gi][gj] = float(dur_m)
                    static_duration_min[gi][gj] = float(static_m if static_m is not None else dur_m)
                    seen_pairs.add((gi, gj))

        for i in range(n):
            for j in range(n):
                if i != j and (i, j) not in seen_pairs:
                    raise RuntimeError(f"Incomplete computeRouteMatrix response missing ({i}->{j})")

        calc_at = datetime.now(timezone.utc).isoformat()
        data_source = _matrix_data_source(google_mode, optimization_objective)
        is_live = data_source == DATA_SOURCE_GOOGLE_LIVE_TRAFFIC
        result = CostMatrixResult(
            nodes=nodes,
            straightLineKm=straight_line,
            distanceKm=distance_km,
            durationMinutes=duration_min,
            staticDurationMinutes=static_duration_min,
            seed=int(seed),
            distanceMultiplier=1.0,
            travelMode=travel_mode,
            speedKmh=get_simulated_speed_kmh(google_mode),
            cacheHit=False,
            matrixKey=cache_key,
            optimizationObjective=optimization_objective,
            provider="google_maps",
            providerLabel="Google Maps",
            dataSource=data_source,  # type: ignore[arg-type]
            isLiveTraffic=is_live,
            durationType="live_traffic" if is_live else "estimated_road_duration",
            durationLabel=(
                "Live traffic travel duration (Google Routes API)"
                if is_live
                else "Static road travel duration (Google Routes API)"
            ),
            trafficCalculatedAt=calc_at,
            calculatedAt=calc_at,
            fallbackReason=None,
            providerAttempts=[],
            roadDistanceAvailable=True,
        )

        with _CACHE_LOCK:
            if len(_GOOGLE_MATRIX_CACHE) >= MAX_CACHE_ENTRIES:
                _GOOGLE_MATRIX_CACHE.popitem(last=False)
            _GOOGLE_MATRIX_CACHE[cache_key] = (time.monotonic() + ttl, result)

        return result
    except Exception as exc:
        raise RuntimeError(redact_secrets(str(exc))) from exc


def fetch_google_route_geometry(
    waypoints: list[dict],
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> dict[str, Any]:
    """
    Fetch an actual road polyline and traffic/static durations from Google Routes API computeRoutes.
    Raises RuntimeError on missing key, rate-limit, or upstream error.
    """
    api_key = get_google_server_api_key()
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured.")

    google_mode = resolve_google_travel_mode(travel_mode)
    use_shorter_ref = optimization_objective == OBJECTIVE_SHORTEST_DISTANCE and google_mode in (
        "DRIVE",
        "TWO_WHEELER",
    )
    wp_sig = "|".join(f"{float(w['latitude']):.6f},{float(w['longitude']):.6f}" for w in waypoints)
    cache_key = f"geom|google|{google_mode}|{optimization_objective}|{wp_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _GOOGLE_GEOMETRY_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_payload = cached
            if now < expires_at:
                _GOOGLE_GEOMETRY_CACHE.move_to_end(cache_key)
                return {**cached_payload, "cacheHit": True}
            _GOOGLE_GEOMETRY_CACHE.pop(cache_key, None)

    if not _check_rate_limit():
        raise RuntimeError("Google Routes API rate limit guard reached.")

    origin = {
        "location": {
            "latLng": {
                "latitude": float(waypoints[0]["latitude"]),
                "longitude": float(waypoints[0]["longitude"]),
            }
        }
    }
    destination = {
        "location": {
            "latLng": {
                "latitude": float(waypoints[-1]["latitude"]),
                "longitude": float(waypoints[-1]["longitude"]),
            }
        }
    }
    intermediates = [
        {
            "location": {
                "latLng": {
                    "latitude": float(w["latitude"]),
                    "longitude": float(w["longitude"]),
                }
            }
        }
        for w in waypoints[1:-1]
    ]

    body: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "travelMode": google_mode,
    }
    if intermediates:
        body["intermediates"] = intermediates
    if google_mode in ("DRIVE", "TWO_WHEELER"):
        body["routingPreference"] = "TRAFFIC_AWARE"
    if use_shorter_ref:
        body["requestedReferenceRoutes"] = ["SHORTER_DISTANCE"]

    field_mask_parts = [
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.staticDuration",
    ]
    if use_shorter_ref:
        field_mask_parts.extend(["routes.routeLabels", "routes.routeToken"])

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-Maps-Solution-ID": ATTRIBUTION_SOLUTION_ID,
        "X-Goog-FieldMask": ",".join(field_mask_parts),
    }

    try:
        t0 = time.perf_counter()
        resp = requests.post(COMPUTE_ROUTES_URL, json=body, headers=headers, timeout=15.0)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        log_api_request(
            provider="google_routes",
            endpoint="computeRoutes",
            status_code=resp.status_code,
            success=resp.status_code == 200,
            duration_ms=elapsed_ms,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Google computeRoutes HTTP {resp.status_code}")

        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            raise RuntimeError("No routes returned by computeRoutes")

        chosen = routes[0]
        if use_shorter_ref:
            shorter = next(
                (r for r in routes if "SHORTER_DISTANCE" in (r.get("routeLabels") or [])),
                None,
            )
            if shorter is not None:
                chosen = shorter

        meters = float(chosen.get("distanceMeters") or 0.0)
        dur_m = _parse_duration_minutes(chosen.get("duration")) or 0.0
        static_m = _parse_duration_minutes(chosen.get("staticDuration")) or dur_m
        encoded_polyline = (chosen.get("polyline") or {}).get("encodedPolyline")
        calc_at = datetime.now(timezone.utc).isoformat()
        data_source = _matrix_data_source(google_mode, optimization_objective)
        is_live = data_source == DATA_SOURCE_GOOGLE_LIVE_TRAFFIC

        payload = {
            "provider": "google_maps",
            "providerLabel": "Google Maps",
            "encodedPolyline": encoded_polyline,
            "dataSource": data_source,
            "isLiveTraffic": is_live,
            "durationType": "live_traffic" if is_live else "estimated_road_duration",
            "durationLabel": (
                "Live traffic travel duration (Google Routes API)"
                if is_live
                else "Static road travel duration (Google Routes API)"
            ),
            "trafficCalculatedAt": calc_at,
            "calculatedAt": calc_at,
            "distanceKm": round(meters / 1000.0, 3),
            "durationMinutes": round(dur_m, 2),
            "staticDurationMinutes": round(static_m, 2),
            "trafficDelayMinutes": (
                round(max(0.0, dur_m - static_m), 2) if is_live else 0.0
            ),
            "routeLabels": chosen.get("routeLabels") or [],
            "fallbackReason": None,
            "cacheHit": False,
        }

        with _CACHE_LOCK:
            if len(_GOOGLE_GEOMETRY_CACHE) >= MAX_CACHE_ENTRIES:
                _GOOGLE_GEOMETRY_CACHE.popitem(last=False)
            _GOOGLE_GEOMETRY_CACHE[cache_key] = (time.monotonic() + ttl, payload)

        return payload
    except Exception as exc:
        raise RuntimeError(redact_secrets(str(exc))) from exc


def get_maps_status() -> dict[str, Any]:
    from app.services.routing_service import get_routing_status

    return get_routing_status()


def build_cost_matrix_with_google_or_fallback(
    nodes: list[dict],
    seed: int = 42,
    distance_multiplier: float = 1.0,
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> CostMatrixResult:
    from app.services.routing_service import build_cost_matrix_with_routing

    return build_cost_matrix_with_routing(
        nodes,
        seed=seed,
        distance_multiplier=distance_multiplier,
        travel_mode=travel_mode,
        optimization_objective=optimization_objective,
    )


def compute_google_route_geometry(
    waypoints: list[dict],
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> dict[str, Any]:
    from app.services.routing_service import compute_route_geometry_with_routing

    return compute_route_geometry_with_routing(
        waypoints,
        travel_mode=travel_mode,
        optimization_objective=optimization_objective,
    )
