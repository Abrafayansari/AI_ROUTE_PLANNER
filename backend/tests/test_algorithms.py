from __future__ import annotations

import pytest

from app.algorithms import (
    run_astar,
    run_bfs,
    run_csp_scheduler,
    run_genetic_algorithm,
    run_kmeans,
    run_ucs,
    validate_permutation,
)
from app.utils.metrics import (
    build_local_cost_matrix,
    clear_matrix_cache,
    haversine_km,
)

SAMPLE_NODES = [
    {"id": "office", "name": "Central Office", "latitude": 30.2672, "longitude": -97.7431, "isOffice": True},
    {"id": "d1", "name": "North Stop", "latitude": 30.3075, "longitude": -97.7422, "isOffice": False},
    {"id": "d2", "name": "Northeast Stop", "latitude": 30.2965, "longitude": -97.7048, "isOffice": False},
    {"id": "d3", "name": "East Stop", "latitude": 30.2641, "longitude": -97.7215, "isOffice": False},
    {"id": "d4", "name": "South Stop", "latitude": 30.2098, "longitude": -97.7712, "isOffice": False},
    {"id": "d5", "name": "West Stop", "latitude": 30.2784, "longitude": -97.8012, "isOffice": False},
]


def test_haversine_and_matrix_caching():
    clear_matrix_cache()
    d = haversine_km(30.2672, -97.7431, 30.3075, -97.7422)
    assert 4.0 < d < 5.0

    m1 = build_local_cost_matrix(SAMPLE_NODES, seed=42, distance_multiplier=1.25)
    m2 = build_local_cost_matrix(SAMPLE_NODES, seed=42, distance_multiplier=1.25)
    assert m1.cacheHit is False
    assert m2.cacheHit is True
    assert m1.distanceKm == m2.distanceKm


def test_bfs_ucs_and_astar_comparison():
    matrix = build_local_cost_matrix(SAMPLE_NODES, seed=77, distance_multiplier=1.25)
    bfs = run_bfs(matrix, return_to_office=True)
    ucs = run_ucs(matrix, return_to_office=True)
    astar = run_astar(matrix, return_to_office=True)

    assert bfs["completed"] is True
    assert ucs["completed"] is True
    assert astar["completed"] is True

    # BFS minimizes edge count, NOT weighted distance
    assert bfs["edgeCount"] == len(SAMPLE_NODES)
    assert bfs["isInformed"] is False
    assert "edge" in bfs["objectiveDescription"].lower()

    # UCS is uninformed cost-based; A* is informed with admissible MST heuristic
    assert ucs["isInformed"] is False
    assert astar["isInformed"] is True
    assert astar["totalCost"] == pytest.approx(ucs["totalCost"], abs=1e-6)
    assert astar["nodesExpanded"] <= ucs["nodesExpanded"]

    # Fixed office start and return
    assert ucs["routeOrder"][0] == 0 and ucs["routeOrder"][-1] == 0
    assert astar["routeOrder"][0] == 0 and astar["routeOrder"][-1] == 0


def test_hand_checkable_4_node_graph():
    hand_nodes = [
        {"id": "0", "name": "Office", "latitude": 0.0, "longitude": 0.0, "isOffice": True},
        {"id": "1", "name": "A", "latitude": 0.0, "longitude": 0.01, "isOffice": False},
        {"id": "2", "name": "B", "latitude": 0.0, "longitude": 0.09, "isOffice": False},
        {"id": "3", "name": "C", "latitude": 0.0, "longitude": 0.02, "isOffice": False},
    ]
    matrix = build_local_cost_matrix(hand_nodes, seed=1, distance_multiplier=1.0)
    bfs = run_bfs(matrix, True)
    ucs = run_ucs(matrix, True)
    astar = run_astar(matrix, True)

    assert ucs["totalCost"] == pytest.approx(astar["totalCost"], abs=1e-6)
    assert ucs["totalCost"] <= bfs["totalCost"] + 1e-9


def test_exact_search_cap_beyond_12_distributors():
    large_nodes = [
        {"id": f"n{i}", "name": f"Node {i}", "latitude": 30.2 + i * 0.01, "longitude": -97.7 - i * 0.01, "isOffice": i == 0}
        for i in range(14)
    ]
    matrix = build_local_cost_matrix(large_nodes, seed=10, distance_multiplier=1.1)
    bfs = run_bfs(matrix, True)
    ucs = run_ucs(matrix, True)
    astar = run_astar(matrix, True)
    ga = run_genetic_algorithm(matrix, True, seed=10, population_size=30, generations=30)

    assert bfs["completed"] is False and "capped" in bfs["warning"].lower()
    assert ucs["completed"] is False and "capped" in ucs["warning"].lower()
    assert astar["completed"] is False and "capped" in astar["warning"].lower()
    assert ga["completed"] is True
    assert validate_permutation(ga["routeOrder"][1:-1], 13) is True


def test_genetic_algorithm_permutations_closed_and_open():
    matrix = build_local_cost_matrix(SAMPLE_NODES, seed=42, distance_multiplier=1.25)
    ga_return = run_genetic_algorithm(
        matrix, return_to_office=True, seed=42, population_size=60, generations=100
    )
    assert ga_return["completed"] is True
    assert ga_return["isHeuristic"] is True
    assert ga_return["routeOrder"][0] == 0
    assert ga_return["routeOrder"][-1] == 0
    assert validate_permutation(ga_return["routeOrder"][1:-1], len(SAMPLE_NODES) - 1)

    ga_one_way = run_genetic_algorithm(
        matrix, return_to_office=False, seed=42, population_size=60, generations=100
    )
    assert ga_one_way["routeOrder"][0] == 0
    assert len(ga_one_way["routeOrder"]) == len(SAMPLE_NODES)
    assert validate_permutation(ga_one_way["routeOrder"][1:], len(SAMPLE_NODES) - 1)


def test_kmeans_reproducibility_and_k_validation():
    points = [
        {
            "id": n["id"],
            "name": n["name"],
            "latitude": n["latitude"],
            "longitude": n["longitude"],
        }
        for n in SAMPLE_NODES[1:]
    ]
    r1 = run_kmeans(points, 2, seed=42)
    r2 = run_kmeans(points, 2, seed=42)
    assert r1["assignments"] == r2["assignments"]
    assert len(r1["centroids"]) == 2
    assert r1["converged"] is True

    with pytest.raises(ValueError):
        run_kmeans(points, 0)
    with pytest.raises(ValueError):
        run_kmeans(points, len(points) + 1)


def test_csp_scheduler_constraints_and_failure_reasons():
    result = run_csp_scheduler(
        [
            {
                "id": "d-ok-1",
                "name": "Morning Account",
                "priority": 5,
                "visitDurationMinutes": 45,
                "openingTime": "09:00",
                "closingTime": "11:30",
            },
            {
                "id": "d-ok-2",
                "name": "Afternoon Account",
                "priority": 3,
                "visitDurationMinutes": 60,
                "openingTime": "13:30",
                "closingTime": "17:00",
            },
            {
                "id": "d-impossible",
                "name": "Night-Only Warehouse",
                "priority": 4,
                "visitDurationMinutes": 45,
                "openingTime": "18:00",
                "closingTime": "22:00",
            },
        ],
        {
            "workStartTime": "09:00",
            "workEndTime": "17:00",
            "slotIncrementMinutes": 15,
            "travelBufferMinutes": 15,
            "lunchBreakEnabled": True,
            "lunchStartTime": "12:30",
            "lunchDurationMinutes": 60,
            "maxVisitsPerDay": 8,
        },
    )

    assert len(result["scheduled"]) == 2
    assert len(result["unscheduled"]) == 1
    assert result["unscheduled"][0]["distributorId"] == "d-impossible"
    assert "opening hours" in result["unscheduled"][0]["reason"]

    first, second = result["scheduled"]
    assert first["endMinutes"] + 15 <= second["startMinutes"]
