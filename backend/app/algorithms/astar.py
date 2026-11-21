from __future__ import annotations

import heapq
import math
import time

from app.utils.metrics import CostMatrixResult, evaluate_route_metrics

DEFAULT_MAX_NODES_EXPANDED = 150_000
MAX_EXACT_DISTRIBUTORS = 12


def _compute_mst_weight(
    unvisited_mask: int,
    num_distributors: int,
    weights: list[list[float]],
    mst_cache: dict[int, float],
) -> float:
    cached = mst_cache.get(unvisited_mask)
    if cached is not None:
        return cached

    nodes = [d + 1 for d in range(num_distributors) if (unvisited_mask & (1 << d)) != 0]
    m = len(nodes)
    if m <= 1:
        mst_cache[unvisited_mask] = 0.0
        return 0.0

    in_tree = [False] * m
    min_edge = [math.inf] * m
    min_edge[0] = 0.0
    total = 0.0

    for _ in range(m):
        u_idx = -1
        best = math.inf
        for i in range(m):
            if not in_tree[i] and min_edge[i] < best:
                best = min_edge[i]
                u_idx = i
        if u_idx == -1:
            break
        in_tree[u_idx] = True
        total += best
        u_node = nodes[u_idx]
        for v_idx in range(m):
            if not in_tree[v_idx]:
                w = weights[u_node][nodes[v_idx]]
                if w < min_edge[v_idx]:
                    min_edge[v_idx] = w

    mst_cache[unvisited_mask] = total
    return total


def _compute_admissible_heuristic(
    current_node: int,
    visited_mask: int,
    full_mask: int,
    num_distributors: int,
    return_to_office: bool,
    weights: list[list[float]],
    mst_cache: dict[int, float],
) -> float:
    unvisited_mask = full_mask ^ visited_mask
    if unvisited_mask == 0:
        return weights[current_node][0] if (return_to_office and current_node != 0) else 0.0

    min_entry = math.inf
    min_exit = math.inf if return_to_office else 0.0

    for d in range(num_distributors):
        if (unvisited_mask & (1 << d)) != 0:
            node_idx = d + 1
            entry_cost = weights[current_node][node_idx]
            if entry_cost < min_entry:
                min_entry = entry_cost
            if return_to_office:
                exit_cost = weights[node_idx][0]
                if exit_cost < min_exit:
                    min_exit = exit_cost

    mst = _compute_mst_weight(unvisited_mask, num_distributors, weights, mst_cache)
    return min_entry + mst + min_exit


def run_astar(
    matrix: CostMatrixResult,
    return_to_office: bool = True,
    max_nodes_expanded: int = DEFAULT_MAX_NODES_EXPANDED,
) -> dict:
    """
    Week 4: A* Search — INFORMED heuristic search.
    Uses f(n) = g(n) + h(n) with admissible 1-tree/MST + min-entry + min-exit lower bound.
    Optimal for non-negative edge weights and expands <= nodes compared to UCS.
    """
    start_t = time.perf_counter()
    num_distributors = len(matrix.nodes) - 1
    objective_description = (
        "Informed search minimizing total simulated distance using f(n) = g(n) + h(n) with admissible MST + entry/exit lower-bound heuristic."
    )

    if num_distributors <= 0:
        return {
            "algorithm": "A*",
            "isInformed": True,
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
            "algorithm": "A*",
            "isInformed": True,
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
            "warning": f"Exact A* capped at {MAX_EXACT_DISTRIBUTORS} distributors due to exponential TSP state space (n * 2^n). Use Genetic Algorithm for larger instances.",
        }

    full_mask = (1 << num_distributors) - 1
    weights = matrix.distanceKm
    mst_cache: dict[int, float] = {}

    def encode_state(node: int, mask: int, returned: int) -> int:
        return (returned << 20) | (node << 14) | mask

    best_g: dict[int, float] = {}
    parent_map: dict[int, tuple[int | None, int]] = {}

    start_key = encode_state(0, 0, 0)
    best_g[start_key] = 0.0
    parent_map[start_key] = (None, 0)

    h0 = _compute_admissible_heuristic(
        0, 0, full_mask, num_distributors, return_to_office, weights, mst_cache
    )
    tie = 0
    heap: list[tuple[float, int, int, int, int, int, float]] = [
        (h0, tie, start_key, 0, 0, 0, 0.0)
    ]
    nodes_expanded = 0

    while heap:
        _, _, key, node, mask, returned, g = heapq.heappop(heap)
        known_best = best_g.get(key)
        if known_best is not None and g > known_best + 1e-9:
            continue

        if nodes_expanded >= max_nodes_expanded:
            return {
                "algorithm": "A*",
                "isInformed": True,
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
                "warning": f"A* expansion limit ({max_nodes_expanded}) reached before finding optimal goal.",
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
                "algorithm": "A*",
                "isInformed": True,
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
                        h = _compute_admissible_heuristic(
                            next_node,
                            next_mask,
                            full_mask,
                            num_distributors,
                            return_to_office,
                            weights,
                            mst_cache,
                        )
                        tie += 1
                        heapq.heappush(
                            heap,
                            (next_g + h, tie, next_key, next_node, next_mask, 0, next_g),
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
        "algorithm": "A*",
        "isInformed": True,
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
