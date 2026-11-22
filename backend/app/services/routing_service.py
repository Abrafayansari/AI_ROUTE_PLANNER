from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import os
import threading
import time
from typing import Any

from flask import current_app, has_app_context
import requests

from app.config import redact_secrets
from app.services.db_service import log_api_request
from app.services.google_maps_service import (
    OBJECTIVE_FASTEST_TIME,
    OBJECTIVE_SHORTEST_DISTANCE,
    clear_google_maps_caches,
    fetch_google_cost_matrix,
    fetch_google_route_geometry,
    get_google_server_api_key,
)
from app.utils.metrics import (
    CostMatrixResult,
    OptimizationObjective,
    TravelMode,
    build_local_cost_matrix,
    get_simulated_speed_kmh,
)

DATA_SOURCE_OSRM_OSM = "osrm_osm"
DATA_SOURCE_OPENROUTESERVICE = "openrouteservice"

DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"
DEFAULT_OSRM_PROFILE = "driving"
DEFAULT_ORS_BASE_URL = "https://api.openrouteservice.org"

OSRM_USER_AGENT = "SmartRoutePlanner/1.0 (+https://github.com/smart-route-planner; OSRM demo policy compliant)"
PUBLIC_OSRM_MIN_INTERVAL_SEC = 1.05

MAX_CACHE_ENTRIES = 100
TTL_FASTEST_TIME_SEC = 300.0
TTL_SHORTEST_DISTANCE_SEC = 1800.0

_ROUTING_LOCK = threading.Lock()
_OSRM_RATE_LOCK = threading.Lock()
_LAST_PUBLIC_OSRM_CALL_AT = 0.0

_OSRM_MATRIX_CACHE: OrderedDict[str, tuple[float, CostMatrixResult]] = OrderedDict()
_OSRM_GEOMETRY_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_ORS_MATRIX_CACHE: OrderedDict[str, tuple[float, CostMatrixResult]] = OrderedDict()
_ORS_GEOMETRY_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()


class AllRoutingProvidersFailedError(RuntimeError):
    """Raised when every configured real-road routing provider fails or is unavailable."""

    def __init__(self, message: str, attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(redact_secrets(message))
        self.attempts = attempts or []

    def to_details(self) -> dict[str, Any]:
        return {"attempts": self.attempts}


def clear_routing_caches() -> None:
    clear_google_maps_caches()
    with _ROUTING_LOCK:
        _OSRM_MATRIX_CACHE.clear()
        _OSRM_GEOMETRY_CACHE.clear()
        _ORS_MATRIX_CACHE.clear()
        _ORS_GEOMETRY_CACHE.clear()
    global _LAST_PUBLIC_OSRM_CALL_AT
    with _OSRM_RATE_LOCK:
        _LAST_PUBLIC_OSRM_CALL_AT = 0.0


def get_osrm_base_url() -> str:
    val = None
    if has_app_context():
        val = current_app.config.get("OSRM_BASE_URL")
    if not val:
        val = os.getenv("OSRM_BASE_URL")
    cleaned = str(val or DEFAULT_OSRM_BASE_URL).strip().rstrip("/")
    return cleaned or DEFAULT_OSRM_BASE_URL


def get_osrm_profile() -> str:
    val = None
    if has_app_context():
        val = current_app.config.get("OSRM_PROFILE")
    if not val:
        val = os.getenv("OSRM_PROFILE")
    cleaned = str(val or DEFAULT_OSRM_PROFILE).strip().strip("/")
    return cleaned or DEFAULT_OSRM_PROFILE


def get_ors_api_key() -> str | None:
    from app.config import is_placeholder_api_key

    val = None
    if has_app_context():
        val = current_app.config.get("OPENROUTESERVICE_API_KEY")
    if not val:
        val = os.getenv("OPENROUTESERVICE_API_KEY")
    cleaned = str(val or "").strip()
    if not cleaned or is_placeholder_api_key(cleaned):
        return None
    return cleaned


def get_ors_base_url() -> str:
    val = None
    if has_app_context():
        val = current_app.config.get("OPENROUTESERVICE_BASE_URL")
    if not val:
        val = os.getenv("OPENROUTESERVICE_BASE_URL")
    cleaned = str(val or DEFAULT_ORS_BASE_URL).strip().rstrip("/")
    return cleaned or DEFAULT_ORS_BASE_URL


def resolve_ors_profile(travel_mode: str | None) -> str:
    if travel_mode in ("WALK", "simulated_walking"):
        return "foot-walking"
    return "driving-car"


def _throttle_public_osrm_if_needed(base_url: str) -> None:
    """Respect public OSRM demo server usage policy (~1 req/sec) when hitting router.project-osrm.org."""
    global _LAST_PUBLIC_OSRM_CALL_AT
    if "router.project-osrm.org" not in base_url:
        return
    # Skip sleep if requests.get is monkeypatched in unit tests
    if not getattr(requests.get, "__module__", "").startswith("requests"):
        return
    with _OSRM_RATE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_PUBLIC_OSRM_CALL_AT
        if _LAST_PUBLIC_OSRM_CALL_AT > 0 and elapsed < PUBLIC_OSRM_MIN_INTERVAL_SEC:
            time.sleep(PUBLIC_OSRM_MIN_INTERVAL_SEC - elapsed)
        _LAST_PUBLIC_OSRM_CALL_AT = time.monotonic()


def get_routing_status() -> dict[str, Any]:
    google_server_configured = bool(get_google_server_api_key())
    client_configured = bool(str(os.getenv("VITE_GOOGLE_MAPS_API_KEY") or "").strip())
    ors_configured = bool(get_ors_api_key())
    osrm_base_url = get_osrm_base_url()
    osrm_profile = get_osrm_profile()

    priority = ["osrm"]
    if google_server_configured:
        priority.insert(0, "google_maps")
    if ors_configured:
        priority.append("openrouteservice")

    active_default_provider = "google_maps" if google_server_configured else "osrm"
    active_default_label = (
        "Google Maps" if google_server_configured else "OSRM / OpenStreetMap"
    )

    return {
        "serverConfigured": google_server_configured,
        "googleServerConfigured": google_server_configured,
        "clientKeyConfigured": client_configured,
        "osrmEnabled": True,
        "osrmBaseUrl": osrm_base_url,
        "osrmProfile": osrm_profile,
        "openRouteServiceConfigured": ors_configured,
        "providerPriority": priority,
        "provider": active_default_provider,
        "providerLabel": active_default_label,
        "fallbackActive": not google_server_configured,
        "supportedObjectives": [OBJECTIVE_FASTEST_TIME, OBJECTIVE_SHORTEST_DISTANCE],
        "defaultObjective": OBJECTIVE_FASTEST_TIME,
    }


def fetch_osrm_cost_matrix(
    nodes: list[dict],
    seed: int = 42,
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> CostMatrixResult:
    """
    Fetch directed N x N road distance (km) and estimated travel duration (minutes)
    from OSRM /table/v1/{profile}/... endpoint.
    Note: OSRM provides estimated normal road durations (no live traffic).
    """
    base_url = get_osrm_base_url()
    profile = get_osrm_profile()
    n = len(nodes)
    coord_sig = "|".join(
        f"{nd['id']}:{float(nd['latitude']):.6f},{float(nd['longitude']):.6f}" for nd in nodes
    )
    cache_key = f"osrm|{base_url}|{profile}|{optimization_objective}|{coord_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _ROUTING_LOCK:
        cached = _OSRM_MATRIX_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_res = cached
            if now < expires_at:
                _OSRM_MATRIX_CACHE.move_to_end(cache_key)
                return CostMatrixResult(
                    nodes=cached_res.nodes,
                    straightLineKm=cached_res.straightLineKm,
                    distanceKm=cached_res.distanceKm,
                    durationMinutes=cached_res.durationMinutes,
                    staticDurationMinutes=cached_res.staticDurationMinutes,
                    seed=cached_res.seed,
                    distanceMultiplier=1.0,
                    travelMode=travel_mode,
                    speedKmh=cached_res.speedKmh,
                    cacheHit=True,
                    matrixKey=cached_res.matrixKey,
                    optimizationObjective=optimization_objective,
                    provider="osrm",
                    providerLabel="OSRM / OpenStreetMap",
                    dataSource=DATA_SOURCE_OSRM_OSM,
                    isLiveTraffic=False,
                    durationType="estimated_road_duration",
                    durationLabel="Estimated road travel duration (OSRM / OpenStreetMap — no live traffic)",
                    trafficCalculatedAt=None,
                    calculatedAt=cached_res.calculatedAt,
                    fallbackReason=None,
                    providerAttempts=[],
                    roadDistanceAvailable=True,
                )
            _OSRM_MATRIX_CACHE.pop(cache_key, None)

    coords_param = ";".join(
        f"{float(nd['longitude']):.6f},{float(nd['latitude']):.6f}" for nd in nodes
    )
    url = f"{base_url}/table/v1/{profile}/{coords_param}"
    params = {"annotations": "duration,distance"}
    headers = {"User-Agent": OSRM_USER_AGENT}

    _throttle_public_osrm_if_needed(base_url)

    t0 = time.perf_counter()
    resp = requests.get(url, params=params, headers=headers, timeout=15.0)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    log_api_request(
        provider="osrm",
        endpoint=f"/table/v1/{profile}",
        status_code=resp.status_code,
        success=resp.status_code == 200,
        duration_ms=elapsed_ms,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"OSRM table HTTP {resp.status_code}")

    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM table returned code={data.get('code')}: {data.get('message', '')}")

    durations_sec = data.get("durations")
    distances_m = data.get("distances")
    if not isinstance(durations_sec, list) or not isinstance(distances_m, list):
        raise RuntimeError("OSRM table response missing durations or distances matrix.")
    if len(durations_sec) != n or len(distances_m) != n:
        raise RuntimeError("OSRM table response dimension mismatch.")

    distance_km = [[0.0 for _ in range(n)] for _ in range(n)]
    duration_min = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        if len(durations_sec[i]) != n or len(distances_m[i]) != n:
            raise RuntimeError(f"OSRM table row {i} dimension mismatch.")
        for j in range(n):
            if i == j:
                distance_km[i][j] = 0.0
                duration_min[i][j] = 0.0
                continue
            raw_m = distances_m[i][j]
            raw_s = durations_sec[i][j]
            if raw_m is None or raw_s is None:
                raise RuntimeError(f"OSRM could not find a road route for ({i}->{j}).")
            distance_km[i][j] = round(float(raw_m) / 1000.0, 3)
            duration_min[i][j] = round(max(0.0, float(raw_s) / 60.0), 2)

    straight_line = build_local_cost_matrix(
        nodes,
        seed=seed,
        distance_multiplier=1.0,
        travel_mode=travel_mode,
        optimization_objective=optimization_objective,
    ).straightLineKm

    calc_at = datetime.now(timezone.utc).isoformat()
    result = CostMatrixResult(
        nodes=nodes,
        straightLineKm=straight_line,
        distanceKm=distance_km,
        durationMinutes=duration_min,
        staticDurationMinutes=[list(row) for row in duration_min],
        seed=int(seed),
        distanceMultiplier=1.0,
        travelMode=travel_mode,
        speedKmh=get_simulated_speed_kmh(travel_mode),
        cacheHit=False,
        matrixKey=cache_key,
        optimizationObjective=optimization_objective,
        provider="osrm",
        providerLabel="OSRM / OpenStreetMap",
        dataSource=DATA_SOURCE_OSRM_OSM,
        isLiveTraffic=False,
        durationType="estimated_road_duration",
        durationLabel="Estimated road travel duration (OSRM / OpenStreetMap — no live traffic)",
        trafficCalculatedAt=None,
        calculatedAt=calc_at,
        fallbackReason=None,
        providerAttempts=[],
        roadDistanceAvailable=True,
    )

    with _ROUTING_LOCK:
        if len(_OSRM_MATRIX_CACHE) >= MAX_CACHE_ENTRIES:
            _OSRM_MATRIX_CACHE.popitem(last=False)
        _OSRM_MATRIX_CACHE[cache_key] = (time.monotonic() + ttl, result)

    return result


def fetch_osrm_route_geometry(
    waypoints: list[dict],
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> dict[str, Any]:
    """Fetch actual road-following encoded polyline, distance, and duration from OSRM /route/v1/{profile}/."""
    base_url = get_osrm_base_url()
    profile = get_osrm_profile()
    wp_sig = "|".join(f"{float(w['latitude']):.6f},{float(w['longitude']):.6f}" for w in waypoints)
    cache_key = f"geom|osrm|{base_url}|{profile}|{optimization_objective}|{wp_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _ROUTING_LOCK:
        cached = _OSRM_GEOMETRY_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_payload = cached
            if now < expires_at:
                _OSRM_GEOMETRY_CACHE.move_to_end(cache_key)
                return {**cached_payload, "cacheHit": True}
            _OSRM_GEOMETRY_CACHE.pop(cache_key, None)

    coords_param = ";".join(
        f"{float(w['longitude']):.6f},{float(w['latitude']):.6f}" for w in waypoints
    )
    url = f"{base_url}/route/v1/{profile}/{coords_param}"
    params = {"overview": "full", "geometries": "polyline"}
    headers = {"User-Agent": OSRM_USER_AGENT}

    _throttle_public_osrm_if_needed(base_url)

    t0 = time.perf_counter()
    resp = requests.get(url, params=params, headers=headers, timeout=15.0)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    log_api_request(
        provider="osrm",
        endpoint=f"/route/v1/{profile}",
        status_code=resp.status_code,
        success=resp.status_code == 200,
        duration_ms=elapsed_ms,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"OSRM route HTTP {resp.status_code}")

    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM route returned code={data.get('code')}: {data.get('message', '')}")

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("OSRM returned no routes.")

    chosen = routes[0]
    encoded_polyline = chosen.get("geometry")
    if not encoded_polyline:
        raise RuntimeError("OSRM route did not include encoded polyline geometry.")

    meters = float(chosen.get("distance") or 0.0)
    seconds = float(chosen.get("duration") or 0.0)
    dur_min = round(max(0.0, seconds / 60.0), 2)
    calc_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "provider": "osrm",
        "providerLabel": "OSRM / OpenStreetMap",
        "encodedPolyline": encoded_polyline,
        "dataSource": DATA_SOURCE_OSRM_OSM,
        "isLiveTraffic": False,
        "durationType": "estimated_road_duration",
        "durationLabel": "Estimated road travel duration (OSRM / OpenStreetMap — no live traffic)",
        "trafficCalculatedAt": None,
        "calculatedAt": calc_at,
        "distanceKm": round(meters / 1000.0, 3),
        "durationMinutes": dur_min,
        "staticDurationMinutes": dur_min,
        "trafficDelayMinutes": 0.0,
        "routeLabels": ["OSRM_DRIVING"],
        "fallbackReason": None,
        "cacheHit": False,
    }

    with _ROUTING_LOCK:
        if len(_OSRM_GEOMETRY_CACHE) >= MAX_CACHE_ENTRIES:
            _OSRM_GEOMETRY_CACHE.popitem(last=False)
        _OSRM_GEOMETRY_CACHE[cache_key] = (time.monotonic() + ttl, payload)

    return payload


def fetch_ors_cost_matrix(
    nodes: list[dict],
    seed: int = 42,
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> CostMatrixResult:
    """
    Fetch directed N x N road distance (km) and estimated travel duration (minutes)
    from OpenRouteService /v2/matrix/{profile} when OPENROUTESERVICE_API_KEY is configured.
    """
    api_key = get_ors_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTESERVICE_API_KEY is not configured.")

    base_url = get_ors_base_url()
    profile = resolve_ors_profile(travel_mode)
    n = len(nodes)
    coord_sig = "|".join(
        f"{nd['id']}:{float(nd['latitude']):.6f},{float(nd['longitude']):.6f}" for nd in nodes
    )
    cache_key = f"ors|{base_url}|{profile}|{optimization_objective}|{coord_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _ROUTING_LOCK:
        cached = _ORS_MATRIX_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_res = cached
            if now < expires_at:
                _ORS_MATRIX_CACHE.move_to_end(cache_key)
                return CostMatrixResult(
                    nodes=cached_res.nodes,
                    straightLineKm=cached_res.straightLineKm,
                    distanceKm=cached_res.distanceKm,
                    durationMinutes=cached_res.durationMinutes,
                    staticDurationMinutes=cached_res.staticDurationMinutes,
                    seed=cached_res.seed,
                    distanceMultiplier=1.0,
                    travelMode=travel_mode,
                    speedKmh=cached_res.speedKmh,
                    cacheHit=True,
                    matrixKey=cached_res.matrixKey,
                    optimizationObjective=optimization_objective,
                    provider="openrouteservice",
                    providerLabel="OpenRouteService",
                    dataSource=DATA_SOURCE_OPENROUTESERVICE,
                    isLiveTraffic=False,
                    durationType="estimated_road_duration",
                    durationLabel="Estimated road travel duration (OpenRouteService — no live traffic)",
                    trafficCalculatedAt=None,
                    calculatedAt=cached_res.calculatedAt,
                    fallbackReason=None,
                    providerAttempts=[],
                    roadDistanceAvailable=True,
                )
            _ORS_MATRIX_CACHE.pop(cache_key, None)

    url = f"{base_url}/v2/matrix/{profile}"
    body = {
        "locations": [[float(nd["longitude"]), float(nd["latitude"])] for nd in nodes],
        "metrics": ["distance", "duration"],
        "units": "m",
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    t0 = time.perf_counter()
    resp = requests.post(url, json=body, headers=headers, timeout=15.0)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    log_api_request(
        provider="openrouteservice",
        endpoint=f"/v2/matrix/{profile}",
        status_code=resp.status_code,
        success=resp.status_code == 200,
        duration_ms=elapsed_ms,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouteService matrix HTTP {resp.status_code}")

    data = resp.json()
    distances_m = data.get("distances")
    durations_sec = data.get("durations")
    if not isinstance(distances_m, list) or not isinstance(durations_sec, list):
        raise RuntimeError("OpenRouteService matrix response missing distances or durations.")
    if len(distances_m) != n or len(durations_sec) != n:
        raise RuntimeError("OpenRouteService matrix dimension mismatch.")

    distance_km = [[0.0 for _ in range(n)] for _ in range(n)]
    duration_min = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                distance_km[i][j] = 0.0
                duration_min[i][j] = 0.0
                continue
            raw_m = distances_m[i][j]
            raw_s = durations_sec[i][j]
            if raw_m is None or raw_s is None:
                raise RuntimeError(f"OpenRouteService could not route ({i}->{j}).")
            distance_km[i][j] = round(float(raw_m) / 1000.0, 3)
            duration_min[i][j] = round(max(0.0, float(raw_s) / 60.0), 2)

    straight_line = build_local_cost_matrix(
        nodes,
        seed=seed,
        distance_multiplier=1.0,
        travel_mode=travel_mode,
        optimization_objective=optimization_objective,
    ).straightLineKm

    calc_at = datetime.now(timezone.utc).isoformat()
    result = CostMatrixResult(
        nodes=nodes,
        straightLineKm=straight_line,
        distanceKm=distance_km,
        durationMinutes=duration_min,
        staticDurationMinutes=[list(row) for row in duration_min],
        seed=int(seed),
        distanceMultiplier=1.0,
        travelMode=travel_mode,
        speedKmh=get_simulated_speed_kmh(travel_mode),
        cacheHit=False,
        matrixKey=cache_key,
        optimizationObjective=optimization_objective,
        provider="openrouteservice",
        providerLabel="OpenRouteService",
        dataSource=DATA_SOURCE_OPENROUTESERVICE,
        isLiveTraffic=False,
        durationType="estimated_road_duration",
        durationLabel="Estimated road travel duration (OpenRouteService — no live traffic)",
        trafficCalculatedAt=None,
        calculatedAt=calc_at,
        fallbackReason=None,
        providerAttempts=[],
        roadDistanceAvailable=True,
    )

    with _ROUTING_LOCK:
        if len(_ORS_MATRIX_CACHE) >= MAX_CACHE_ENTRIES:
            _ORS_MATRIX_CACHE.popitem(last=False)
        _ORS_MATRIX_CACHE[cache_key] = (time.monotonic() + ttl, result)

    return result


def fetch_ors_route_geometry(
    waypoints: list[dict],
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> dict[str, Any]:
    """Fetch road polyline, distance, and duration from OpenRouteService /v2/directions/{profile}."""
    api_key = get_ors_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTESERVICE_API_KEY is not configured.")

    base_url = get_ors_base_url()
    profile = resolve_ors_profile(travel_mode)
    wp_sig = "|".join(f"{float(w['latitude']):.6f},{float(w['longitude']):.6f}" for w in waypoints)
    cache_key = f"geom|ors|{base_url}|{profile}|{optimization_objective}|{wp_sig}"
    ttl = (
        TTL_FASTEST_TIME_SEC
        if optimization_objective == OBJECTIVE_FASTEST_TIME
        else TTL_SHORTEST_DISTANCE_SEC
    )

    now = time.monotonic()
    with _ROUTING_LOCK:
        cached = _ORS_GEOMETRY_CACHE.get(cache_key)
        if cached is not None:
            expires_at, cached_payload = cached
            if now < expires_at:
                _ORS_GEOMETRY_CACHE.move_to_end(cache_key)
                return {**cached_payload, "cacheHit": True}
            _ORS_GEOMETRY_CACHE.pop(cache_key, None)

    url = f"{base_url}/v2/directions/{profile}"
    body = {
        "coordinates": [[float(w["longitude"]), float(w["latitude"])] for w in waypoints],
        "preference": "shortest" if optimization_objective == OBJECTIVE_SHORTEST_DISTANCE else "fastest",
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    t0 = time.perf_counter()
    resp = requests.post(url, json=body, headers=headers, timeout=15.0)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    log_api_request(
        provider="openrouteservice",
        endpoint=f"/v2/directions/{profile}",
        status_code=resp.status_code,
        success=resp.status_code == 200,
        duration_ms=elapsed_ms,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouteService directions HTTP {resp.status_code}")

    data = resp.json()
    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("OpenRouteService directions returned no routes.")

    chosen = routes[0]
    encoded_polyline = chosen.get("geometry")
    if not encoded_polyline or not isinstance(encoded_polyline, str):
        raise RuntimeError("OpenRouteService route missing encoded polyline string.")

    summary = chosen.get("summary") or {}
    meters = float(summary.get("distance") or 0.0)
    seconds = float(summary.get("duration") or 0.0)
    dur_min = round(max(0.0, seconds / 60.0), 2)
    calc_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "provider": "openrouteservice",
        "providerLabel": "OpenRouteService",
        "encodedPolyline": encoded_polyline,
        "dataSource": DATA_SOURCE_OPENROUTESERVICE,
        "isLiveTraffic": False,
        "durationType": "estimated_road_duration",
        "durationLabel": "Estimated road travel duration (OpenRouteService — no live traffic)",
        "trafficCalculatedAt": None,
        "calculatedAt": calc_at,
        "distanceKm": round(meters / 1000.0, 3),
        "durationMinutes": dur_min,
        "staticDurationMinutes": dur_min,
        "trafficDelayMinutes": 0.0,
        "routeLabels": [profile.upper()],
        "fallbackReason": None,
        "cacheHit": False,
    }

    with _ROUTING_LOCK:
        if len(_ORS_GEOMETRY_CACHE) >= MAX_CACHE_ENTRIES:
            _ORS_GEOMETRY_CACHE.popitem(last=False)
        _ORS_GEOMETRY_CACHE[cache_key] = (time.monotonic() + ttl, payload)

    return payload


def build_cost_matrix_with_routing(
    nodes: list[dict],
    seed: int = 42,
    distance_multiplier: float = 1.0,
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> CostMatrixResult:
    """
    Build directed N x N road distance & travel duration matrices using prioritized real-road providers:
      1. Google Routes API (only if GOOGLE_MAPS_API_KEY is configured and succeeds)
      2. OSRM + OpenStreetMap (free fallback)
      3. OpenRouteService (only if OPENROUTESERVICE_API_KEY is configured)
    Raises AllRoutingProvidersFailedError if all configured real-road providers fail.
    Never silently falls back to simulated Haversine estimates.
    """
    if len(nodes) <= 1:
        has_google = bool(get_google_server_api_key())
        calc_at = datetime.now(timezone.utc).isoformat()
        return CostMatrixResult(
            nodes=nodes,
            straightLineKm=[[0.0 for _ in nodes] for _ in nodes],
            distanceKm=[[0.0 for _ in nodes] for _ in nodes],
            durationMinutes=[[0.0 for _ in nodes] for _ in nodes],
            staticDurationMinutes=[[0.0 for _ in nodes] for _ in nodes],
            seed=int(seed),
            distanceMultiplier=1.0,
            travelMode=travel_mode,
            speedKmh=get_simulated_speed_kmh(travel_mode),
            cacheHit=False,
            matrixKey="single-node",
            optimizationObjective=optimization_objective,
            provider="google_maps" if has_google else "osrm",
            providerLabel="Google Maps" if has_google else "OSRM / OpenStreetMap",
            dataSource="google_road_distance" if has_google else DATA_SOURCE_OSRM_OSM,
            isLiveTraffic=False,
            durationType="estimated_road_duration",
            durationLabel="Single-node origin (0 edges)",
            trafficCalculatedAt=calc_at if has_google else None,
            calculatedAt=calc_at,
            fallbackReason=None,
            providerAttempts=[],
            roadDistanceAvailable=True,
        )

    attempts: list[dict[str, Any]] = []
    failover_notes: list[str] = []

    # 1. Google Routes API (optional, only if configured)
    if get_google_server_api_key():
        try:
            res = fetch_google_cost_matrix(
                nodes,
                seed=seed,
                travel_mode=travel_mode,
                optimization_objective=optimization_objective,
            )
            attempts.append({"provider": "google_maps", "status": "succeeded"})
            res.providerAttempts = attempts
            return res
        except Exception as exc:
            err = redact_secrets(str(exc))
            attempts.append({"provider": "google_maps", "status": "failed", "reason": err})
            failover_notes.append(f"Google Maps failed ({err})")
    else:
        attempts.append(
            {
                "provider": "google_maps",
                "status": "skipped",
                "reason": "GOOGLE_MAPS_API_KEY is not configured",
            }
        )

    # 2. OSRM + OpenStreetMap (free default fallback)
    try:
        res = fetch_osrm_cost_matrix(
            nodes,
            seed=seed,
            travel_mode=travel_mode,
            optimization_objective=optimization_objective,
        )
        attempts.append({"provider": "osrm", "status": "succeeded"})
        res.providerAttempts = attempts
        if failover_notes:
            res.fallbackReason = f"{'; '.join(failover_notes)}. Switched to OSRM / OpenStreetMap."
        return res
    except Exception as exc:
        err = redact_secrets(str(exc))
        attempts.append({"provider": "osrm", "status": "failed", "reason": err})
        failover_notes.append(f"OSRM failed ({err})")

    # 3. OpenRouteService (free-tier fallback, only if configured)
    if get_ors_api_key():
        try:
            res = fetch_ors_cost_matrix(
                nodes,
                seed=seed,
                travel_mode=travel_mode,
                optimization_objective=optimization_objective,
            )
            attempts.append({"provider": "openrouteservice", "status": "succeeded"})
            res.providerAttempts = attempts
            res.fallbackReason = f"{'; '.join(failover_notes)}. Switched to OpenRouteService."
            return res
        except Exception as exc:
            err = redact_secrets(str(exc))
            attempts.append({"provider": "openrouteservice", "status": "failed", "reason": err})
            failover_notes.append(f"OpenRouteService failed ({err})")
    else:
        attempts.append(
            {
                "provider": "openrouteservice",
                "status": "skipped",
                "reason": "OPENROUTESERVICE_API_KEY is not configured",
            }
        )

    raise AllRoutingProvidersFailedError(
        "All real-road routing providers failed or are unavailable: "
        + "; ".join(
            f"{a['provider']}: {a.get('reason', a['status'])}" for a in attempts
        ),
        attempts=attempts,
    )


def compute_route_geometry_with_routing(
    waypoints: list[dict],
    travel_mode: TravelMode = "DRIVE",
    optimization_objective: OptimizationObjective = OBJECTIVE_FASTEST_TIME,
) -> dict[str, Any]:
    """
    Fetch actual road-following route geometry across prioritized real-road providers:
      1. Google Routes API (optional, if configured)
      2. OSRM + OpenStreetMap (free fallback)
      3. OpenRouteService (optional, if configured)
    Raises ValueError if fewer than 2 waypoints are provided, or AllRoutingProvidersFailedError if all providers fail.
    """
    if len(waypoints) < 2:
        raise ValueError("At least 2 waypoints are required to compute road geometry.")

    attempts: list[dict[str, Any]] = []
    failover_notes: list[str] = []

    # 1. Google Routes API
    if get_google_server_api_key():
        try:
            payload = fetch_google_route_geometry(
                waypoints,
                travel_mode=travel_mode,
                optimization_objective=optimization_objective,
            )
            attempts.append({"provider": "google_maps", "status": "succeeded"})
            payload["providerAttempts"] = attempts
            return payload
        except Exception as exc:
            err = redact_secrets(str(exc))
            attempts.append({"provider": "google_maps", "status": "failed", "reason": err})
            failover_notes.append(f"Google Maps failed ({err})")
    else:
        attempts.append(
            {
                "provider": "google_maps",
                "status": "skipped",
                "reason": "GOOGLE_MAPS_API_KEY is not configured",
            }
        )

    # 2. OSRM + OpenStreetMap
    try:
        payload = fetch_osrm_route_geometry(
            waypoints,
            travel_mode=travel_mode,
            optimization_objective=optimization_objective,
        )
        attempts.append({"provider": "osrm", "status": "succeeded"})
        payload["providerAttempts"] = attempts
        if failover_notes:
            payload["fallbackReason"] = (
                f"{'; '.join(failover_notes)}. Switched to OSRM / OpenStreetMap."
            )
        return payload
    except Exception as exc:
        err = redact_secrets(str(exc))
        attempts.append({"provider": "osrm", "status": "failed", "reason": err})
        failover_notes.append(f"OSRM failed ({err})")

    # 3. OpenRouteService
    if get_ors_api_key():
        try:
            payload = fetch_ors_route_geometry(
                waypoints,
                travel_mode=travel_mode,
                optimization_objective=optimization_objective,
            )
            attempts.append({"provider": "openrouteservice", "status": "succeeded"})
            payload["providerAttempts"] = attempts
            payload["fallbackReason"] = (
                f"{'; '.join(failover_notes)}. Switched to OpenRouteService."
            )
            return payload
        except Exception as exc:
            err = redact_secrets(str(exc))
            attempts.append({"provider": "openrouteservice", "status": "failed", "reason": err})
            failover_notes.append(f"OpenRouteService failed ({err})")
    else:
        attempts.append(
            {
                "provider": "openrouteservice",
                "status": "skipped",
                "reason": "OPENROUTESERVICE_API_KEY is not configured",
            }
        )

    raise AllRoutingProvidersFailedError(
        "All real-road routing geometry providers failed or are unavailable: "
        + "; ".join(
            f"{a['provider']}: {a.get('reason', a['status'])}" for a in attempts
        ),
        attempts=attempts,
    )
