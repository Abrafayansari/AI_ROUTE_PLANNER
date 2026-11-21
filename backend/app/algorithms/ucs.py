from __future__ import annotations

import heapq
import time

from app.utils.metrics import CostMatrixResult, evaluate_route_metrics

DEFAULT_MAX_NODES_EXPANDED = 150_000
MAX_EXACT_DISTRIBUTORS = 12


def run_ucs(
    matrix: CostMatrixResult,
    return_to_office: bool = True,
    max_nodes_expanded: int = DEFAULT_MAX_NODES_EXPANDED,
) -> dict:
    """
    Week 4 Baseline: Uniform Cost Search (UCS) — UNINFORMED cost-based search.
    Expands states strictly in order of cumulative path cost g(n) without any heuristic.
    Optimal for non-negative edge weights.
    """
    start_t = time.perf_counter()
    num_distributors = len(matrix.nodes) - 1
    objective_description = (
        "Uninformed cost-based search minimizing cumulative simulated distance g(n) without a heuristic."
    )

    if num_distributors <= 0:
        return {
            "algorithm": "UCS",
            "isInformed": False,
            "isOptimalForObjective": True,
            "objectiveDescription": objective_description,
            "routeOrder": [0],
            "totalCost": 0.0,
            "estimatedDistanceKm": 0.0,
            "estimatedDurationMinutes": 0.0,
            "edgeCount": 0,
            "nodesExpanded": 1,
            "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
            "completed": True,
        }

    if num_distributors > MAX_EXACT_DISTRIBUTORS:
        return {
            "algorithm": "UCS",
            "isInformed": False,
            "isOptimalForObjective": False,
            "objectiveDescription": objective_description,
            "routeOrder": [],
            "totalCost": 0.0,
            "estimatedDistanceKm": 0.0,
            "estimatedDurationMinutes": 0.0,
            "edgeCount": 0,
            "nodesExpanded": 0,
            "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
            "completed": False,
            "warning": f"Exact UCS capped at {MAX_EXACT_DISTRIBUTORS} distributors due to exponential TSP state space (n * 2^n). Use Genetic Algorithm for larger instances.",
        }

    full_mask = (1 << num_distributors) - 1
    weights = matrix.distanceKm

    def encode_state(node: int, mask: int, returned: int) -> int:
        return (returned << 20) | (node << 14) | mask

    best_g: dict[int, float] = {}
    parent_map: dict[int, tuple[int | None, int]] = {}

    start_key = encode_state(0, 0, 0)
    best_g[start_key] = 0.0
    parent_map[start_key] = (None, 0)

    # Heap entries: (priority_g, tie_counter, key, node, mask, returned, g)
    tie = 0
    heap: list[tuple[float, int, int, int, int, int, float]] = [
        (0.0, tie, start_key, 0, 0, 0, 0.0)
    ]
    nodes_expanded = 0

    while heap:
        _, _, key, node, mask, returned, g = heapq.heappop(heap)
        known_best = best_g.get(key)
        if known_best is not None and g > known_best + 1e-9:
            continue

        if nodes_expanded >= max_nodes_expanded:
            return {
                "algorithm": "UCS",
                "isInformed": False,
                "isOptimalForObjective": False,
                "objectiveDescription": objective_description,
                "routeOrder": [],
                "totalCost": 0.0,
                "estimatedDistanceKm": 0.0,
                "estimatedDurationMinutes": 0.0,
                "edgeCount": 0,
                "nodesExpanded": nodes_expanded,
                "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
                "completed": False,
                "warning": f"UCS expansion limit ({max_nodes_expanded}) reached before finding optimal goal.",
            }

        nodes_expanded += 1
        is_goal = mask == full_mask and (not return_to_office or returned == 1)

        if is_goal:
            route_order: list[int] = []
            cursor: int | None = key
            while cursor is not None:
                entry = parent_map.get(cursor)
                if entry is None:
                    break
                prev_key, cur_node = entry
                route_order.append(cur_node)
                cursor = prev_key
            route_order.reverse()

            metrics = evaluate_route_metrics(matrix, route_order)
            return {
                "algorithm": "UCS",
                "isInformed": False,
                "isOptimalForObjective": True,
                "objectiveDescription": objective_description,
                "routeOrder": route_order,
                "totalCost": metrics["totalDistanceKm"],
                "estimatedDistanceKm": metrics["totalDistanceKm"],
                "estimatedDurationMinutes": metrics["totalDurationMinutes"],
                "edgeCount": metrics["edgeCount"],
                "nodesExpanded": nodes_expanded,
                "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
                "completed": True,
            }

        if mask < full_mask:
            for d in range(num_distributors):
                if (mask & (1 << d)) == 0:
                    next_node = d + 1
                    next_mask = mask | (1 << d)
                    next_key = encode_state(next_node, next_mask, 0)
                    next_g = g + weights[node][next_node]
                    prev_best = best_g.get(next_key)
                    if prev_best is None or next_g + 1e-9 < prev_best:
                        best_g[next_key] = next_g
                        parent_map[next_key] = (key, next_node)
                        tie += 1
                        heapq.heappush(
                            heap, (next_g, tie, next_key, next_node, next_mask, 0, next_g)
                        )
        elif return_to_office and returned == 0:
            next_key = encode_state(0, mask, 1)
            next_g = g + weights[node][0]
            prev_best = best_g.get(next_key)
            if prev_best is None or next_g + 1e-9 < prev_best:
                best_g[next_key] = next_g
                parent_map[next_key] = (key, 0)
                tie += 1
                heapq.heappush(heap, (next_g, tie, next_key, 0, mask, 1, next_g))

    return {
        "algorithm": "UCS",
        "isInformed": False,
        "isOptimalForObjective": False,
        "objectiveDescription": objective_description,
        "routeOrder": [],
        "totalCost": 0.0,
        "estimatedDistanceKm": 0.0,
        "estimatedDurationMinutes": 0.0,
        "edgeCount": 0,
        "nodesExpanded": nodes_expanded,
        "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
        "completed": False,
        "warning": "No valid route found.",
    }
