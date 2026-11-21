from __future__ import annotations

from collections import deque
import time

from app.utils.metrics import CostMatrixResult, evaluate_route_metrics

DEFAULT_MAX_NODES_EXPANDED = 150_000
MAX_EXACT_DISTRIBUTORS = 12


def run_bfs(
    matrix: CostMatrixResult,
    return_to_office: bool = True,
    max_nodes_expanded: int = DEFAULT_MAX_NODES_EXPANDED,
) -> dict:
    """
    Week 3: Uninformed Search — Breadth-First Search (BFS).
    Explores states level-by-level in FIFO order and minimizes edge/hop count,
    NOT weighted simulated travel distance.
    """
    start_t = time.perf_counter()
    num_distributors = len(matrix.nodes) - 1

    if num_distributors <= 0:
        return {
            "algorithm": "BFS",
            "isInformed": False,
            "isOptimalForObjective": True,
            "objectiveDescription": "Uninformed search minimizing edge/hop count (ignores travel distance weights).",
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
            "algorithm": "BFS",
            "isInformed": False,
            "isOptimalForObjective": False,
            "objectiveDescription": "Uninformed search minimizing edge/hop count (ignores travel distance weights).",
            "routeOrder": [],
            "totalCost": 0.0,
            "estimatedDistanceKm": 0.0,
            "estimatedDurationMinutes": 0.0,
            "edgeCount": 0,
            "nodesExpanded": 0,
            "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
            "completed": False,
            "warning": f"Exact state-space BFS capped at {MAX_EXACT_DISTRIBUTORS} distributors (2^{num_distributors} state space). Use Genetic Algorithm for larger tours.",
        }

    full_mask = (1 << num_distributors) - 1

    def encode_state(node: int, mask: int, returned: int) -> int:
        return (returned << 20) | (node << 14) | mask

    visited: set[int] = {encode_state(0, 0, 0)}
    queue: deque[tuple[int, int, int, list[int]]] = deque([(0, 0, 0, [0])])
    nodes_expanded = 0

    while queue:
        if nodes_expanded >= max_nodes_expanded:
            return {
                "algorithm": "BFS",
                "isInformed": False,
                "isOptimalForObjective": False,
                "objectiveDescription": "Uninformed search minimizing edge/hop count (ignores travel distance weights).",
                "routeOrder": [],
                "totalCost": 0.0,
                "estimatedDistanceKm": 0.0,
                "estimatedDurationMinutes": 0.0,
                "edgeCount": 0,
                "nodesExpanded": nodes_expanded,
                "executionTimeMs": round((time.perf_counter() - start_t) * 1000.0, 3),
                "completed": False,
                "warning": f"BFS expansion limit ({max_nodes_expanded}) reached before finding goal.",
            }

        node, mask, returned, path = queue.popleft()
        nodes_expanded += 1

        is_goal = mask == full_mask and (not return_to_office or returned == 1)
        if is_goal:
            metrics = evaluate_route_metrics(matrix, path)
            return {
                "algorithm": "BFS",
                "isInformed": False,
                "isOptimalForObjective": True,
                "objectiveDescription": "Uninformed search minimizing edge/hop count (does NOT minimize simulated travel distance).",
                "routeOrder": path,
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
                    key = encode_state(next_node, next_mask, 0)
                    if key not in visited:
                        visited.add(key)
                        queue.append((next_node, next_mask, 0, path + [next_node]))
        elif return_to_office and returned == 0:
            key = encode_state(0, mask, 1)
            if key not in visited:
                visited.add(key)
                queue.append((0, mask, 1, path + [0]))

    return {
        "algorithm": "BFS",
        "isInformed": False,
        "isOptimalForObjective": False,
        "objectiveDescription": "Uninformed search minimizing edge/hop count.",
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
