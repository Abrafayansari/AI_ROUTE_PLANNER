from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
import math
from typing import Literal, TypedDict
import numpy as np

TravelMode = Literal[
    "simulated_vehicle",
    "simulated_walking",
    "simulated_van",
    "DRIVE",
    "TWO_WHEELER",
    "WALK",
]
OptimizationObjective = Literal["FASTEST_TIME", "SHORTEST_DISTANCE"]
RoutingProviderType = Literal["google_maps", "osrm", "openrouteservice", "simulated_fallback"]
DataSourceType = Literal[
    "google_live_traffic",
    "google_road_distance",
    "osrm_osm",
    "openrouteservice",
    "simulated_fallback",
]

EARTH_RADIUS_KM = 6371.0
MAX_CACHE_SIZE = 100


class GraphNode(TypedDict, total=False):
    id: str
    name: str
    latitude: float
    longitude: float
    isOffice: bool
    visitDurationMinutes: int


@dataclass
class CostMatrixResult:
    nodes: list[dict]
    straightLineKm: list[list[float]]
    distanceKm: list[list[float]]
    durationMinutes: list[list[float]]
    seed: int
    distanceMultiplier: float
    travelMode: TravelMode
    speedKmh: float
    cacheHit: bool
    matrixKey: str
    staticDurationMinutes: list[list[float]] | None = None
    optimizationObjective: OptimizationObjective = "FASTEST_TIME"
    provider: RoutingProviderType = "simulated_fallback"
    providerLabel: str = "Simulated Local Graph"
    dataSource: DataSourceType = "simulated_fallback"
    isLiveTraffic: bool = False
    durationType: Literal["live_traffic", "estimated_road_duration", "simulated"] = "simulated"
    durationLabel: str = "Simulated straight-line estimate"
    trafficCalculatedAt: str | None = None
    calculatedAt: str | None = None
    fallbackReason: str | None = None
    providerAttempts: list[dict] = field(default_factory=list)
    roadDistanceAvailable: bool = False

    def __post_init__(self) -> None:
        if self.staticDurationMinutes is None:
            self.staticDurationMinutes = [list(row) for row in self.durationMinutes]

    def to_dict(self) -> dict:
        return asdict(self)


def mulberry32(seed: int):
    """Deterministic 32-bit PRNG matching seeded simulation semantics."""
    state = [seed & 0xFFFFFFFF]

    def _next_random() -> float:
        a = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        state[0] = a
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return _next_random


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle Haversine distance in kilometers using numpy/math."""
    lat1_r, lon1_r, lat2_r, lon2_r = np.radians([lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * (np.sin(dlon / 2.0) ** 2)
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(max(0.0, float(1.0 - a))))
    return float(EARTH_RADIUS_KM * c)


haversine_distance_km = haversine_km


def get_simulated_speed_kmh(mode: str) -> float:
    if mode in ("simulated_walking", "WALK"):
        return 5.0
    if mode == "simulated_van":
        return 28.0
    if mode == "TWO_WHEELER":
        return 30.0
    return 35.0


_MATRIX_CACHE: OrderedDict[str, dict] = OrderedDict()


def clear_matrix_cache() -> None:
    _MATRIX_CACHE.clear()


def build_local_cost_matrix(
    nodes: list[dict],
    seed: int = 42,
    distance_multiplier: float = 1.25,
    travel_mode: TravelMode = "simulated_vehicle",
    optimization_objective: OptimizationObjective = "FASTEST_TIME",
    fallback_reason: str | None = None,
) -> CostMatrixResult:
    clamped_mult = max(1.0, min(3.0, float(distance_multiplier)))
    speed_kmh = get_simulated_speed_kmh(travel_mode)

    coord_signature = "|".join(
        f"{n['id']}:{float(n['latitude']):.6f},{float(n['longitude']):.6f}"
        for n in nodes
    )
    matrix_key = f"{seed}|{clamped_mult:.3f}|{travel_mode}|{optimization_objective}|{coord_signature}"

    cached = _MATRIX_CACHE.get(matrix_key)
    if cached is not None:
        _MATRIX_CACHE.move_to_end(matrix_key)
        payload = dict(cached)
        if fallback_reason is not None:
            payload["fallbackReason"] = fallback_reason
        return CostMatrixResult(cacheHit=True, **payload)

    n = len(nodes)
    straight_line = np.zeros((n, n), dtype=float)
    distance_km = np.zeros((n, n), dtype=float)
    duration_min = np.zeros((n, n), dtype=float)

    rng = mulberry32(int(seed))

    for i in range(n):
        for j in range(i + 1, n):
            raw = haversine_km(
                float(nodes[i]["latitude"]),
                float(nodes[i]["longitude"]),
                float(nodes[j]["latitude"]),
                float(nodes[j]["longitude"]),
            )
            local_detour_factor = 1.0 + rng() * 0.18
            sim_dist = round(raw * clamped_mult * local_detour_factor, 3)
            sim_min = round((sim_dist / speed_kmh) * 60.0, 2)
            raw_rounded = round(raw, 3)

            straight_line[i, j] = raw_rounded
            straight_line[j, i] = raw_rounded

            distance_km[i, j] = sim_dist
            distance_km[j, i] = sim_dist

            duration_min[i, j] = sim_min
            duration_min[j, i] = sim_min

    payload = {
        "nodes": nodes,
        "straightLineKm": straight_line.tolist(),
        "distanceKm": distance_km.tolist(),
        "durationMinutes": duration_min.tolist(),
        "staticDurationMinutes": duration_min.tolist(),
        "seed": int(seed),
        "distanceMultiplier": clamped_mult,
        "travelMode": travel_mode,
        "speedKmh": speed_kmh,
        "matrixKey": matrix_key,
        "optimizationObjective": optimization_objective,
        "dataSource": "simulated_fallback",
        "trafficCalculatedAt": None,
        "fallbackReason": fallback_reason,
        "roadDistanceAvailable": False,
    }

    if len(_MATRIX_CACHE) >= MAX_CACHE_SIZE:
        _MATRIX_CACHE.popitem(last=False)
    _MATRIX_CACHE[matrix_key] = payload

    return CostMatrixResult(cacheHit=False, **payload)


def resolve_objective(
    matrix: CostMatrixResult, optimization_objective: str | None = None
) -> OptimizationObjective:
    obj = optimization_objective or matrix.optimizationObjective or "FASTEST_TIME"
    return "SHORTEST_DISTANCE" if obj == "SHORTEST_DISTANCE" else "FASTEST_TIME"


def get_objective_weights(
    matrix: CostMatrixResult, optimization_objective: str | None = None
) -> tuple[list[list[float]], OptimizationObjective]:
    resolved = resolve_objective(matrix, optimization_objective)
    if resolved == "SHORTEST_DISTANCE":
        return matrix.distanceKm, resolved
    return matrix.durationMinutes, resolved


def evaluate_route_metrics(
    matrix: CostMatrixResult,
    route_order: list[int],
    optimization_objective: str | None = None,
) -> dict:
    resolved_obj = resolve_objective(matrix, optimization_objective)
    static_mat = matrix.staticDurationMinutes or matrix.durationMinutes
    dist = 0.0
    dur = 0.0
    static_dur = 0.0
    for i in range(len(route_order) - 1):
        u = route_order[i]
        v = route_order[i + 1]
        dist += matrix.distanceKm[u][v]
        dur += matrix.durationMinutes[u][v]
        static_dur += static_mat[u][v]
    traffic_delay = max(0.0, dur - static_dur) if matrix.dataSource == "google_live_traffic" else 0.0
    objective_cost = dist if resolved_obj == "SHORTEST_DISTANCE" else dur
    return {
        "totalDistanceKm": round(dist, 3),
        "totalDurationMinutes": round(dur, 2),
        "totalStaticDurationMinutes": round(static_dur, 2),
        "trafficDelayMinutes": round(traffic_delay, 2),
        "objectiveCost": round(objective_cost, 3),
        "optimizationObjective": resolved_obj,
        "edgeCount": max(0, len(route_order) - 1),
    }


def time_to_minutes(hhmm: str) -> int:
    parts = hhmm.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(mins: int) -> str:
    h = int(math.floor(mins // 60))
    m = int(mins % 60)
    return f"{h:02d}:{m:02d}"
